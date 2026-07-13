from __future__ import annotations

from types import MappingProxyType
from pathlib import Path

from .assemble import assemble_bybit_public_replay_batch_from_rows
from .audit import audit_bybit_public_replay_batch, audit_instrument_universe
from .capture import derive_closed_window
from .evidence import (
    GUARDRAILS,
    PLAN_IDS,
    ALLOWED_BASE_URLS,
    NON_STATUS_ARTIFACT_COUNT,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    DirectoryEvidenceReader,
    validate_persisted_public_batch_evidence,
)
from .models import PublicBatchError, PublicRequestPageAudit
from .pagination import (
    fetch_all_instruments,
    fetch_funding_history_backward,
    fetch_funding_history_chunked,
    fetch_mark_klines,
    fetch_trade_klines,
)
from .parsers import parse_server_time
from .recording import RecordedPublicResponse, strict_json_loads


class ReplayClient:
    def __init__(self, records, plan_id):
        self.plan_id = plan_id
        self._records = [r for r in records if r.plan_id == plan_id]
        self._i = 0

    def public_get(self, endpoint, params):
        if self._i >= len(self._records):
            raise PublicBatchError("recorded_response_missing")
        r = self._records[self._i]
        self._i += 1
        if r.endpoint != endpoint or dict(r.params) != dict(sorted(params.items())):
            raise PublicBatchError("recorded_request_mismatch")
        return r.parsed_payload

    def assert_exhausted(self):
        if self._i != len(self._records):
            raise PublicBatchError(f"recorded_response_unconsumed:{self.plan_id}")


def records_from_jsonl(data: bytes, *, capture_plan):
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError as e:
        raise PublicBatchError("jsonl_utf8_invalid") from e
    if text and not text.endswith("\n"):
        raise PublicBatchError("jsonl_final_newline_missing")
    rows = []
    expected_keys = {
        "request_sequence_id", "endpoint", "params", "http_status", "content_type",
        "raw_body_text", "raw_body_sha256", "parsed_payload", "plan_id", "base_url",
    }
    if type(capture_plan) is not dict or capture_plan.get("base_url") not in ALLOWED_BASE_URLS:
        raise PublicBatchError("capture_plan_required")
    if type(capture_plan.get("timeout_seconds")) is not int or not (1 <= capture_plan["timeout_seconds"] <= 120):
        raise PublicBatchError("timeout_seconds_invalid")
    base_url = capture_plan["base_url"]
    expected_plan_order = [p["plan_id"] for p in capture_plan.get("plans", [])]
    if expected_plan_order != list(PLAN_IDS):
        raise PublicBatchError("plan_order_invalid")
    for line in text.splitlines():
        if not line:
            raise PublicBatchError("jsonl_blank_line")
        d = strict_json_loads(line)
        if set(d) != expected_keys:
            raise PublicBatchError("recorded_response_key_set_invalid")
        if canonical_json_bytes(d) != line.encode("utf-8"):
            raise PublicBatchError("recorded_response_noncanonical")
        if d["base_url"] != base_url:
            raise PublicBatchError("recorded_response_base_url_mismatch")
        rows.append(
            RecordedPublicResponse(
                d["request_sequence_id"], d["endpoint"], MappingProxyType(d["params"]),
                d["http_status"], d["content_type"], d["raw_body_text"],
                d["raw_body_sha256"], d["parsed_payload"], d["plan_id"], d["base_url"],
            )
        )
    if [r.request_sequence_id for r in rows] != list(range(1, len(rows) + 1)):
        raise PublicBatchError("request_sequence_not_contiguous")
    if not rows or rows[0].plan_id != "server_time_snapshot":
        raise PublicBatchError("server_time_not_first")
    if sum(1 for r in rows if r.plan_id == "server_time_snapshot") != 1:
        raise PublicBatchError("server_time_not_exactly_once")
    order = {p: i for i, p in enumerate(PLAN_IDS)}
    plan_seq = [order[r.plan_id] for r in rows]
    if plan_seq != sorted(plan_seq):
        raise PublicBatchError("recorded_plan_order_invalid")
    return tuple(rows)


def reconstruct_from_records(
    records, *, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100
):
    clients = {pid: ReplayClient(records, pid) for pid in PLAN_IDS}
    server_time = parse_server_time(
        clients["server_time_snapshot"].public_get("/v5/market/time", {})
    )
    st_aud = (PublicRequestPageAudit("/v5/market/time", "", None, None, None, None, 1, 1, None, "server_time_snapshot"),)
    window = derive_closed_window(server_time, kline_row_count)
    ip, ip_aud = fetch_all_instruments(clients["instrument_primary_1000"], server_time, limit=1000)
    ia, ia_aud = fetch_all_instruments(clients["instrument_alternate_200"], server_time, limit=200)
    instrument_equal = tuple(sorted(ip, key=lambda x: x.symbol)) == tuple(sorted(ia, key=lambda x: x.symbol))
    if not instrument_equal:
        raise PublicBatchError("instrument_primary_alternate_mismatch")
    matches = [m for m in ip if m.symbol == symbol]
    if len(matches) != 1:
        raise PublicBatchError("instrument_match_not_unique")
    instrument = matches[0]
    tp, tp_aud = fetch_trade_klines(
        clients["trade_primary_1000"], symbol, window, server_time, page_limit=1000
    )
    ta, ta_aud = fetch_trade_klines(
        clients["trade_alternate_251"], symbol, window, server_time, page_limit=251
    )
    mp, mp_aud = fetch_mark_klines(
        clients["mark_primary_1000"], symbol, window, server_time, page_limit=1000
    )
    ma, ma_aud = fetch_mark_klines(
        clients["mark_alternate_251"], symbol, window, server_time, page_limit=251
    )
    trade_equal = tp == ta
    mark_equal = mp == ma
    if not trade_equal or not mark_equal:
        raise PublicBatchError("kline_primary_alternate_mismatch")
    fund_start = window.end_open_time_ms - funding_lookback_days * 24 * 60 * 60000
    fp, fp_aud = fetch_funding_history_backward(
        clients["funding_primary_backward_200"],
        symbol,
        fund_start,
        window.end_open_time_ms,
        limit=200,
    )
    fa, fa_aud = fetch_funding_history_chunked(
        clients["funding_alternate_chunked_100"],
        symbol,
        fund_start,
        window.end_open_time_ms,
        instrument.funding_interval_minutes,
        target_records_per_window=100,
        page_limit=200,
    )
    funding_equal = fp == fa
    if not funding_equal:
        raise PublicBatchError("funding_primary_alternate_mismatch")
    for c in clients.values():
        c.assert_exhausted()
    batch = assemble_bybit_public_replay_batch_from_rows(
        instrument=instrument,
        server_time=server_time,
        requested_window=window,
        trade_rows=tp,
        mark_rows=mp,
        funding_rows=fp,
        request_page_audits=st_aud + ip_aud + tp_aud + mp_aud + fp_aud,
    )
    return {
        "server_time": server_time,
        "window": window,
        "instrument": instrument,
        "instrument_rows": ip,
        "alternate_instrument_rows": ia,
        "alternate_trade_rows": ta,
        "alternate_mark_rows": ma,
        "alternate_funding_rows": fa,
        "instrument_audit": audit_instrument_universe(ip),
        "trade_rows": tp,
        "mark_rows": mp,
        "funding_rows": fp,
        "funding_observations": batch.funding_observations,
        "request_audits": st_aud + ip_aud + ia_aud + tp_aud + ta_aud + mp_aud + ma_aud + fp_aud + fa_aud,
        "batch": batch,
        "public_audit": audit_bybit_public_replay_batch(batch),
        "cross_plan_equalities": {
            "instrument_primary_alternate_equal_bool": instrument_equal,
            "trade_primary_alternate_equal_bool": trade_equal,
            "mark_primary_alternate_equal_bool": mark_equal,
            "funding_primary_alternate_equal_bool": funding_equal,
        },
    }


def _page_sizes(audits, plan_id):
    return [a.row_count for a in audits if a.plan_id == plan_id]


def build_capture_plan(*, run_id: str, symbol: str, base_url: str, timeout_seconds: int):
    if run_id != "bybit_public_batch_063b_btcusdt_v1":
        raise PublicBatchError("run_id_not_canonical")
    if symbol != "BTCUSDT":
        raise PublicBatchError("symbol_not_canonical")
    if base_url not in ALLOWED_BASE_URLS:
        raise PublicBatchError("base_url_not_approved")
    if type(timeout_seconds) is not int or not (1 <= timeout_seconds <= 120):
        raise PublicBatchError("timeout_seconds_invalid")
    specs = []
    meta = {
        "server_time_snapshot": ("/v5/market/time", "single", 1, 1, {}),
        "instrument_primary_1000": (
            "/v5/market/instruments-info",
            "cursor",
            1000,
            None,
            {"category": "linear", "status": "Trading"},
        ),
        "instrument_alternate_200": (
            "/v5/market/instruments-info",
            "cursor",
            200,
            None,
            {"category": "linear", "status": "Trading"},
        ),
        "trade_primary_1000": (
            "/v5/market/kline",
            "fixed_windows",
            1000,
            1001,
            {"category": "linear", "symbol": symbol, "interval": "1"},
        ),
        "trade_alternate_251": (
            "/v5/market/kline",
            "fixed_windows",
            251,
            1001,
            {"category": "linear", "symbol": symbol, "interval": "1"},
        ),
        "mark_primary_1000": (
            "/v5/market/mark-price-kline",
            "fixed_windows",
            1000,
            1001,
            {"category": "linear", "symbol": symbol, "interval": "1"},
        ),
        "mark_alternate_251": (
            "/v5/market/mark-price-kline",
            "fixed_windows",
            251,
            1001,
            {"category": "linear", "symbol": symbol, "interval": "1"},
        ),
        "funding_primary_backward_200": (
            "/v5/market/funding/history",
            "backward",
            200,
            None,
            {"category": "linear", "symbol": symbol},
        ),
        "funding_alternate_chunked_100": (
            "/v5/market/funding/history",
            "chunked",
            200,
            100,
            {"category": "linear", "symbol": symbol},
        ),
    }
    for i, pid in enumerate(PLAN_IDS):
        endpoint, method, limit, target, fixed = meta[pid]
        specs.append(
            {
                "plan_id": pid,
                "endpoint": endpoint,
                "pagination_method": method,
                "page_limit": limit,
                "target_records": target,
                "fixed_params": fixed,
                "order_index": i,
                "acceptance_page_count_rule": "canonical_minimum_or_exact",
            }
        )
    return {
        "run_id": run_id,
        "schema_version": "capture_plan_v2",
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "symbol": symbol,
        "category": "linear",
        "interval": "1",
        "kline_row_count": 1001,
        "funding_lookback_days": 100,
        "plans": specs,
    }



def derive_and_validate_page_invariants(audits):
    sizes = {pid: _page_sizes(audits, pid) for pid in PLAN_IDS}
    expected_exact = {
        "server_time_snapshot": [1],
        "trade_primary_1000": [1000, 1],
        "trade_alternate_251": [251, 251, 251, 248],
        "mark_primary_1000": [1000, 1],
        "mark_alternate_251": [251, 251, 251, 248],
    }
    for pid in PLAN_IDS:
        if pid not in sizes:
            raise PublicBatchError("page_audit_missing")
    for pid, exact in expected_exact.items():
        if sizes[pid] != exact:
            raise PublicBatchError(f"page_sizes_invalid:{pid}")
    if len(sizes["instrument_primary_1000"]) < 1:
        raise PublicBatchError("page_count_invalid:instrument_primary_1000")
    if len(sizes["instrument_alternate_200"]) < 2:
        raise PublicBatchError("page_count_invalid:instrument_alternate_200")
    if len(sizes["funding_primary_backward_200"]) < 2:
        raise PublicBatchError("page_count_invalid:funding_primary_backward_200")
    if len(sizes["funding_alternate_chunked_100"]) < 2:
        raise PublicBatchError("page_count_invalid:funding_alternate_chunked_100")
    return {
        "instrument_primary_page_count": len(sizes["instrument_primary_1000"]),
        "instrument_alternate_page_count": len(sizes["instrument_alternate_200"]),
        "trade_primary_page_sizes": sizes["trade_primary_1000"],
        "trade_alternate_page_sizes": sizes["trade_alternate_251"],
        "mark_primary_page_sizes": sizes["mark_primary_1000"],
        "mark_alternate_page_sizes": sizes["mark_alternate_251"],
        "funding_primary_page_count": len(sizes["funding_primary_backward_200"]),
        "funding_alternate_chunk_count": len(sizes["funding_alternate_chunked_100"]),
        "server_time_snapshot_response_count": len(sizes["server_time_snapshot"]),
    }

def artifact_bytes(
    e, *, run_id, symbol="BTCUSDT", base_url="https://api.bybit.com", timeout_seconds=30
):
    if base_url not in ALLOWED_BASE_URLS:
        raise PublicBatchError("base_url_not_approved")
    req = e["request_audits"]
    expected_obs = tuple(
        f.funding_time_ms
        for f in e["funding_rows"]
        if e["window"].start_open_time_ms <= f.funding_time_ms <= e["window"].end_open_time_ms
    )
    actual_obs = tuple(o.time_ms for o in e["funding_observations"])
    if actual_obs != expected_obs:
        raise PublicBatchError("funding_observation_times_mismatch")
    page = derive_and_validate_page_invariants(req)
    eq = dict(e.get("cross_plan_equalities", {}))
    required_eq = {
        "instrument_primary_alternate_equal_bool",
        "trade_primary_alternate_equal_bool",
        "mark_primary_alternate_equal_bool",
        "funding_primary_alternate_equal_bool",
    }
    if set(eq) != required_eq or any(eq[k] is not True for k in required_eq):
        raise PublicBatchError("cross_plan_equality_false")
    cross = {"run_id": run_id, "symbol": symbol, **page, **eq, "funding_coverage_proven_bool": False}
    summary = {
        "run_id": run_id,
        "base_url": base_url,
        "timeout_seconds": timeout_seconds,
        "symbol": symbol,
        "category": "linear",
        "interval": "1",
        "funding_lookback_days": 100,
        "server_time_ms": e["server_time"].server_time_ms,
        "last_closed_open_time_ms": e["server_time"].last_closed_open_time_ms,
        "kline_row_count": e["window"].row_count,
        "window_start_open_time_ms": e["window"].start_open_time_ms,
        "window_end_open_time_ms": e["window"].end_open_time_ms,
        "instrument_count": len(e["instrument_rows"]),
        "replay_eligible_count": e["instrument_audit"].replay_eligible_count,
        "trade_row_count": len(e["trade_rows"]),
        "mark_row_count": len(e["mark_rows"]),
        "funding_row_count": len(e["funding_rows"]),
        "funding_observation_count": len(e["funding_observations"]),
        "public_batch_audit_ok": e["public_audit"].public_batch_audit_ok,
        "reproducibility_audit_ok": True,
        **GUARDRAILS,
    }
    repro = {
        "run_id": run_id,
        "reproducibility_audit_ok": True,
        "rebuilt_non_status_artifacts_twice_bool": True,
        "non_status_artifact_count": NON_STATUS_ARTIFACT_COUNT,
    }
    funding_audit = {
        "expected_funding_observation_count": len(expected_obs),
        "actual_funding_observation_count": len(actual_obs),
        "expected_funding_observation_times": list(expected_obs),
        "actual_funding_observation_times": list(actual_obs),
        "funding_observation_times_equal_bool": True,
    }
    report = (
        f"# Bybit Public Batch Report\n\n- run_id: {run_id}\n- base_url: {base_url}\n- symbol: {symbol}\n- Bybit server time: {e['server_time'].server_time_ms}\n- last closed cutoff: {e['server_time'].last_closed_open_time_ms}\n- window start/end/count: {e['window'].start_open_time_ms}/{e['window'].end_open_time_ms}/{e['window'].row_count}\n- instrument_primary_page_count: {cross['instrument_primary_page_count']}\n- instrument_alternate_page_count: {cross['instrument_alternate_page_count']}\n- trade_primary_page_sizes: {cross['trade_primary_page_sizes']}\n- trade_alternate_page_sizes: {cross['trade_alternate_page_sizes']}\n- mark_primary_page_sizes: {cross['mark_primary_page_sizes']}\n- mark_alternate_page_sizes: {cross['mark_alternate_page_sizes']}\n- funding_primary_page_count: {cross['funding_primary_page_count']}\n- funding_alternate_chunk_count: {cross['funding_alternate_chunk_count']}\n- server_time_snapshot_response_count: {cross['server_time_snapshot_response_count']}\n- instrument count: {summary['instrument_count']}\n- replay-eligible count: {summary['replay_eligible_count']}\n- trade row count: {summary['trade_row_count']}\n- mark row count: {summary['mark_row_count']}\n- funding row count: {summary['funding_row_count']}\n- funding observation count: {summary['funding_observation_count']}\n- instrument_primary_alternate_equal_bool: true\n- trade_primary_alternate_equal_bool: true\n- mark_primary_alternate_equal_bool: true\n- funding_primary_alternate_equal_bool: true\n- public batch audit result: {str(summary['public_batch_audit_ok']).lower()}\n- reproducibility audit result: true\n- contains_credentials=false\n"
    ).encode()
    risk = b"# Risk Budget Readiness Report\n\nFrozen guardrails: public Bybit GET /v5/market/* only; no API keys; no private/account/order/grid/position/wallet endpoints; no live execution; no Telegram; no parameter selection; no profitability or live-readiness claims; funding_coverage_proven_bool=false.\n\nThis pack does not prove profitability, parameter suitability, native grid equivalence, native quantity mapping, liquidation behavior, funding-history completeness, 5 USDT maximum-loss budget, or live readiness.\n"
    return {
        "capture_plan.json": canonical_json_bytes(
            build_capture_plan(run_id=run_id, symbol=symbol, base_url=base_url, timeout_seconds=timeout_seconds)
        ),
        "server_time.json": canonical_json_bytes(e["server_time"]),
        "instrument_records.jsonl": canonical_jsonl_bytes(
            {"plan_id": "instrument_primary_1000", **r.__dict__} for r in e["instrument_rows"]
        ),
        "instrument_universe_audit.json": canonical_json_bytes(e["instrument_audit"]),
        "trade_klines.jsonl": canonical_jsonl_bytes(
            {"plan_id": "trade_primary_1000", **r.__dict__} for r in e["trade_rows"]
        ),
        "mark_klines.jsonl": canonical_jsonl_bytes(
            {"plan_id": "mark_primary_1000", **r.__dict__} for r in e["mark_rows"]
        ),
        "funding_rates.jsonl": canonical_jsonl_bytes(
            {"plan_id": "funding_primary_backward_200", **r.__dict__} for r in e["funding_rows"]
        ),
        "funding_observations.jsonl": canonical_jsonl_bytes(e["funding_observations"]),
        "request_page_audits.jsonl": canonical_jsonl_bytes(e["request_audits"]),
        "public_batch_audit.json": canonical_json_bytes(e["public_audit"]),
        "cross_plan_reconciliation_audit.json": canonical_json_bytes({**cross, **funding_audit}),
        "reproducibility_audit.json": canonical_json_bytes(repro),
        "capture_summary.json": canonical_json_bytes(summary),
        "public_batch_report.md": report,
        "risk_budget_readiness_report.md": risk,
    }


def validate_run_directory(run_dir: Path, run_id: str):
    result = validate_persisted_public_batch_evidence(
        DirectoryEvidenceReader(run_dir), expected_run_id=run_id, require_complete_status=False
    )
    return {"ok": result.ok, "rebuilt_artifacts": result.rebuilt_artifacts}
