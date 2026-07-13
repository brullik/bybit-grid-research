from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from bybit_grid.data.public_batch.evidence import (
    ALLOWED_BASE_URLS,
    CANONICAL_MEMBERS,
    GUARDRAILS,
    DirectoryEvidenceReader,
    build_manifest,
    canonical_json_bytes,
    read_json,
    validate_persisted_public_batch_evidence,
    validate_review_pack,
)
from bybit_grid.data.public_batch.models import PublicBatchError
from bybit_grid.data.public_batch.recording import RecordingPublicClient
from bybit_grid.data.public_batch.reconstruct import artifact_bytes, records_from_jsonl, reconstruct_from_records
from scripts import check_bybit_public_batch_review_pack as checker
from scripts import make_bybit_public_batch_review_pack as builder
from scripts import run_bybit_public_batch_evidence as runner

RUN_ID = "bybit_public_batch_063b_btcusdt_v1"
END = 1_700_006_400_000
MINUTE = 60_000
FUNDING_INTERVAL = 480


class Response:
    status = 200
    headers = {"content-type": "application/json; charset=utf-8"}
    def __init__(self, body: str): self._body = body.encode()
    def getcode(self): return self.status
    def read(self): return self._body
    def close(self): pass


def _body(payload):
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return Response(text)


def _instrument(symbol):
    return {
        "symbol": symbol, "contractType": "LinearPerpetual", "status": "Trading", "baseCoin": symbol[:-4],
        "quoteCoin": "USDT", "settleCoin": "USDT", "launchTime": "0", "deliveryTime": "0", "isPreListing": False,
        "fundingInterval": str(FUNDING_INTERVAL),
        "priceFilter": {"tickSize": "0.1"},
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
        "leverageFilter": {"minLeverage": "1", "maxLeverage": "100", "leverageStep": "0.01"},
    }


INSTRUMENTS = [_instrument("BTCUSDT")] + [_instrument(f"COIN{i:03d}USDT") for i in range(1, 201)]
FUNDING_START = END - 100 * 24 * 60 * MINUTE
FUNDING_TIMES = [FUNDING_START + i * FUNDING_INTERVAL * MINUTE for i in range(301)]


def synthetic_client(base_url="https://api.bybit.com"):
    def opener(req, timeout=30):
        parsed = urlparse(req.full_url)
        endpoint = parsed.path
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        top = END + MINUTE
        if endpoint == "/v5/market/time":
            return _body({"retCode": 0, "result": {"timeNano": str(top * 1_000_000), "timeSecond": str(top // 1000)}, "time": top})
        if endpoint == "/v5/market/instruments-info":
            limit = int(q["limit"])
            cursor = q.get("cursor")
            start = int(cursor or 0)
            rows = INSTRUMENTS[start:start + limit]
            nextc = str(start + limit) if start + limit < len(INSTRUMENTS) else ""
            return _body({"retCode": 0, "result": {"category": "linear", "list": rows, "nextPageCursor": nextc}})
        if endpoint in {"/v5/market/kline", "/v5/market/mark-price-kline"}:
            start = int(q["start"])
            end = int(q["end"])
            mark = endpoint.endswith("mark-price-kline")
            rows = []
            for t in range(start, end + 1, MINUTE):
                base = "50000.0" if mark else "50001.0"
                if mark:
                    rows.append([str(t), base, base, base, base])
                else:
                    rows.append([str(t), base, base, base, base, "1.0", "50000.0"])
            return _body({"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT", "list": rows}})
        if endpoint == "/v5/market/funding/history":
            start = int(q["startTime"])
            end = int(q["endTime"])
            limit = int(q["limit"])
            times = [t for t in FUNDING_TIMES if start <= t <= end][-limit:]
            rows = [{"symbol": "BTCUSDT", "fundingRateTimestamp": str(t), "fundingRate": "0.0001"} for t in times]
            return _body({"retCode": 0, "result": {"list": rows}})
        raise AssertionError(endpoint)
    return RecordingPublicClient(base_url=base_url, opener=opener, max_attempts=1, timeout_seconds=30)


def _args(root, base_url):
    return SimpleNamespace(run_id=RUN_ID, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100, output_root=str(root), base_url=base_url, timeout_seconds=30)


@pytest.mark.parametrize("base_url", ALLOWED_BASE_URLS)
def test_full_no_network_lifecycle_for_each_host(tmp_path: Path, capsys, base_url):
    root = tmp_path / "runs"
    out = tmp_path / "pack.zip"
    assert runner._run(_args(root, base_url), client=synthetic_client(base_url))["status"] == "complete"
    run_dir = root / RUN_ID
    assert sorted(p.name for p in run_dir.iterdir()) == sorted(CANONICAL_MEMBERS)
    result = validate_persisted_public_batch_evidence(DirectoryEvidenceReader(run_dir), expected_run_id=RUN_ID, require_complete_status=True)
    assert (result.members, result.source_artifact_count, result.rebuilt_derived_artifact_count, result.non_status_artifact_count) == (18, 1, 15, 16)
    summary = read_json(run_dir / "capture_summary.json")
    assert summary["base_url"] == base_url
    assert summary["reproducibility_audit_ok"] is True
    assert summary["rebuilt_derived_artifacts_twice_bool"] is True
    report = (run_dir / "public_batch_report.md").read_text()
    for line in ["- source_artifact_count: 1", "- derived_artifact_count: 15", "- non_status_artifact_count: 16", "- reproducibility_audit_ok: true", "- rebuilt_derived_artifacts_twice_bool: true"]:
        assert line in report
    records = (run_dir / "recorded_public_responses.jsonl").read_text().splitlines()
    assert [json.loads(r)["request_sequence_id"] for r in records] == list(range(1, len(records) + 1))
    assert {json.loads(r)["base_url"] for r in records} == {base_url}
    assert builder.main(["--run-id", RUN_ID, "--input-root", str(root), "--output", str(out)]) == 0
    assert validate_review_pack(out, RUN_ID)["ok"] is True
    assert checker.main(["--zip", str(out), "--run-id", RUN_ID]) == 0
    captured = capsys.readouterr().out
    assert '"ok":true' in captured


def _evidence_from_synthetic():
    c = synthetic_client()
    from bybit_grid.data.public_batch.capture import run_capture_plans
    from bybit_grid.data.public_batch.reconstruct import build_capture_plan
    from bybit_grid.data.public_batch.evidence import canonical_jsonl_bytes
    run_capture_plans(c, symbol="BTCUSDT", kline_row_count=1001, funding_lookback_days=100)
    plan = build_capture_plan(run_id=RUN_ID, symbol="BTCUSDT", base_url="https://api.bybit.com", timeout_seconds=30)
    return reconstruct_from_records(records_from_jsonl(canonical_jsonl_bytes(c.records), capture_plan=plan))


@pytest.mark.parametrize("phase,mutation,error", [
    ("core", lambda m: (m.pop("server_time.json"), m)[1], "core_derived_artifact_mismatch"),
    ("core", lambda m: {**m, "server_time.json": m["server_time.json"] + b"\n"}, "core_derived_artifact_mismatch"),
    ("final", lambda m: (m.pop("capture_summary.json"), m)[1], "final_derived_artifact_mismatch"),
    ("final", lambda m: {**m, "public_batch_report.md": m["public_batch_report.md"] + b"x"}, "final_derived_artifact_mismatch"),
])
def test_second_build_reproducibility_mismatches_fail_closed(phase, mutation, error):
    def mutate(which, m):
        return mutation(m) if which == phase else m
    with pytest.raises(PublicBatchError, match=error):
        artifact_bytes(_evidence_from_synthetic(), run_id=RUN_ID, mutate_second_build=mutate)


def test_rehashed_summary_and_report_semantic_tamper_rejected(tmp_path: Path):
    root = tmp_path / "runs"
    runner._run(_args(root, "https://api.bybit.com"), client=synthetic_client())
    run_dir = root / RUN_ID
    for name, old, new in [("capture_summary.json", b'"reproducibility_audit_ok":true', b'"reproducibility_audit_ok":false'), ("public_batch_report.md", b"- reproducibility_audit_ok: true", b"- reproducibility_audit_ok: false")]:
        d = tmp_path / name
        d.mkdir()
        for p in run_dir.iterdir():
            (d / p.name).write_bytes(p.read_bytes())
        (d / name).write_bytes((d / name).read_bytes().replace(old, new))
        member_bytes = {n: (d / n).read_bytes() for n in CANONICAL_MEMBERS if n != "review_pack_manifest.json"}
        (d / "review_pack_manifest.json").write_bytes(canonical_json_bytes(build_manifest(member_bytes, run_id=RUN_ID)))
        with pytest.raises(PublicBatchError):
            validate_persisted_public_batch_evidence(DirectoryEvidenceReader(d), expected_run_id=RUN_ID, require_complete_status=True)


def test_risk_report_from_production_artifacts_lists_all_guardrails():
    m = artifact_bytes(_evidence_from_synthetic(), run_id=RUN_ID)
    text = m["risk_budget_readiness_report.md"].decode()
    for k, v in GUARDRAILS.items():
        assert f"- {k}: {str(v).lower()}" in text
