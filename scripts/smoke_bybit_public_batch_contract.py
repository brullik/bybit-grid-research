#!/usr/bin/env python
from __future__ import annotations
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from bybit_grid.data.public_batch.assemble import fetch_bybit_public_replay_batch
from bybit_grid.data.public_batch.audit import audit_bybit_public_replay_batch
from bybit_grid.data.public_batch.models import InclusiveMinuteWindow
from bybit_grid.data.public_batch.parsers import parse_server_time
from bybit_grid.data.public_batch.pagination import (
    fetch_all_instruments,
    fetch_funding_history_backward,
)


class PublicClient:
    base = "https://api.bybit.com"

    def public_get(self, path, params):
        url = self.base + path + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=20) as r:  # noqa: S310 owner-side public smoke only
            return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ns = ap.parse_args()
    c = PublicClient()
    st = parse_server_time(c.public_get("/v5/market/time", {}))
    instruments, ia = fetch_all_instruments(c, st)
    inst = [i for i in instruments if i.symbol == "BTCUSDT" and i.eligible_for_replay()][0]
    recent, fa = fetch_funding_history_backward(
        c,
        "BTCUSDT",
        max(0, st.last_closed_open_time_ms - 14 * 24 * 60 * 60000),
        st.last_closed_open_time_ms,
    )
    older = recent[-2].funding_time_ms if len(recent) > 1 else recent[-1].funding_time_ms
    win = InclusiveMinuteWindow(older - 60000, older + 60000)
    batch = fetch_bybit_public_replay_batch(c, "BTCUSDT", win, server_time=st, instrument=inst)
    audit = audit_bybit_public_replay_batch(batch)
    summary = {
        "status": "ok" if audit.public_batch_audit_ok else "fail",
        "server_time_ms": st.server_time_ms,
        "last_closed_open_time_ms": st.last_closed_open_time_ms,
        "instrument_page_count": len(ia),
        "instrument_count": len(instruments),
        "symbol": "BTCUSDT",
        "funding_interval_minutes": inst.funding_interval_minutes,
        "window_start_open_time_ms": win.start_open_time_ms,
        "window_end_open_time_ms": win.end_open_time_ms,
        "trade_row_count": len(batch.trade_klines),
        "mark_row_count": len(batch.mark_klines),
        "funding_rate_row_count": len(batch.funding_rates),
        "funding_observation_count": len(batch.funding_observations),
        "funding_mark_alignment_method": batch.funding_mark_alignment_method,
        "public_batch_audit_ok": audit.public_batch_audit_ok,
    }
    Path(ns.output).write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
