#!/usr/bin/env python
from __future__ import annotations
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from bybit_grid.data.public_batch.assemble import fetch_bybit_public_replay_batch
from bybit_grid.data.public_batch.audit import audit_bybit_public_replay_batch, audit_instrument_universe
from bybit_grid.data.public_batch.models import InclusiveMinuteWindow, PublicBatchError
from bybit_grid.data.public_batch.pagination import fetch_all_instruments, fetch_funding_history_backward
from bybit_grid.data.public_batch.parsers import parse_server_time

SCHEMA_VERSION = "bybit_public_batch_smoke_063a1_v1"
FALSE_GUARDRAILS = {
    "contains_credentials": False,
    "risk_budget_proven_bool": False,
    "parameter_selection_authorized_bool": False,
    "live_authorized_bool": False,
}


class PublicClient:
    base = "https://api.bybit.com"

    def public_get(self, path, params):
        url = self.base + path + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=20) as r:  # noqa: S310 owner-side public smoke only
            return json.loads(r.read().decode("utf-8"))


def _canonical_write(path, payload):
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    Path(path).write_text(text, encoding="utf-8")
    return text


def _failure(stage, exc):
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "failed",
        "failed_stage": stage,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
        **FALSE_GUARDRAILS,
    }


def _ok_summary(st, instrument_audits, instruments, universe_audit, inst, batch, batch_audit):
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        **FALSE_GUARDRAILS,
        "server_time_ms": st.server_time_ms,
        "last_closed_open_time_ms": st.last_closed_open_time_ms,
        "instrument_page_count": len(instrument_audits),
        "instrument_count": universe_audit.instrument_count,
        "contract_type_counts": dict(universe_audit.contract_type_counts),
        "status_counts": dict(universe_audit.status_counts),
        "quote_coin_counts": dict(universe_audit.quote_coin_counts),
        "settle_coin_counts": dict(universe_audit.settle_coin_counts),
        "zero_funding_interval_count": universe_audit.zero_funding_interval_count,
        "zero_funding_interval_symbols": list(universe_audit.zero_funding_interval_symbols),
        "zero_funding_interval_by_contract_type": dict(universe_audit.zero_funding_interval_by_contract_type),
        "replay_candidate_zero_funding_interval_symbols": list(
            universe_audit.replay_candidate_zero_funding_interval_symbols
        ),
        "replay_eligible_count": universe_audit.replay_eligible_count,
        "universe_audit_ok": universe_audit.universe_audit_ok,
        "symbol": "BTCUSDT",
        "selected_contract_type": inst.contract_type,
        "selected_funding_interval_minutes": inst.funding_interval_minutes,
        "trade_row_count": len(batch.trade_klines),
        "mark_row_count": len(batch.mark_klines),
        "funding_rate_row_count": len(batch.funding_rates),
        "funding_observation_count": len(batch.funding_observations),
        "funding_mark_alignment_method": batch.funding_mark_alignment_method,
        "public_batch_audit_ok": batch_audit.public_batch_audit_ok,
    }


def run_smoke(client):
    stage = "server_time"
    st = parse_server_time(client.public_get("/v5/market/time", {}))
    stage = "instrument_universe"
    instruments, instrument_audits = fetch_all_instruments(client, st)
    universe_audit = audit_instrument_universe(instruments)
    if not universe_audit.universe_audit_ok:
        raise PublicBatchError("instrument_universe_audit_failed")
    candidates = [i for i in instruments if i.symbol == "BTCUSDT" and i.eligible_for_replay()]
    if len(candidates) != 1:
        raise PublicBatchError("BTCUSDT_not_uniquely_replay_eligible")
    inst = candidates[0]
    stage = "funding_history"
    recent, _ = fetch_funding_history_backward(
        client,
        "BTCUSDT",
        max(0, st.last_closed_open_time_ms - 14 * 24 * 60 * 60000),
        st.last_closed_open_time_ms,
    )
    older = recent[-2].funding_time_ms if len(recent) > 1 else recent[-1].funding_time_ms
    win = InclusiveMinuteWindow(older - 60000, older + 60000)
    stage = "public_replay_batch"
    batch = fetch_bybit_public_replay_batch(client, "BTCUSDT", win, server_time=st, instrument=inst)
    batch_audit = audit_bybit_public_replay_batch(batch)
    summary = _ok_summary(st, instrument_audits, instruments, universe_audit, inst, batch, batch_audit)
    if (
        not summary["universe_audit_ok"]
        or summary["replay_candidate_zero_funding_interval_symbols"] != []
        or summary["selected_contract_type"] != "LinearPerpetual"
        or not summary["public_batch_audit_ok"]
        or summary["trade_row_count"] != 3
        or summary["mark_row_count"] != 3
    ):
        raise PublicBatchError("smoke_success_contract_failed")
    return summary, stage


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ns = ap.parse_args()
    stage = "init"
    try:
        summary, stage = run_smoke(PublicClient())
        print(_canonical_write(ns.output, summary))
    except Exception as exc:
        print(_canonical_write(ns.output, _failure(stage, exc)))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
