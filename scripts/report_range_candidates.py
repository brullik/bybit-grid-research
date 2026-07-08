from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.research.range_candidate_summary import read_candidates, build_summary


def main() -> None:
    raw_df = read_candidates(Path("data/processed/range_raw_candidates"))
    event_df = read_candidates(Path("data/processed/range_event_candidates"))
    metrics = {"raw": build_summary(raw_df), "event": build_summary(event_df)}
    metrics_flat = {f"raw_{k}": v for k, v in metrics["raw"].items()}
    metrics_flat.update({f"event_{k}": v for k, v in metrics["event"].items()})
    perf_path = Path("reports/sprint_03_range_candidate_perf.json")
    perf = json.loads(perf_path.read_text()) if perf_path.exists() else {}
    metrics_flat.update({k: v for k, v in perf.items() if k not in metrics_flat})
    out = Path("reports/sprint_03_range_candidate_report.md")
    out.parent.mkdir(exist_ok=True)
    lines = ["# Sprint 03 Range Candidate Report", ""]
    lines += [
        f"- {k}: {v}"
        for k, v in metrics_flat.items()
        if not isinstance(v, list)
    ]
    lines += ["", "## Candidates by lookback window"]
    for r in metrics["raw"].get("candidates_by_lookback", []):
        lines.append(f"- {r['lookback_minutes']}: {r['len']}")
    lines += ["", "## Top 20 symbols by candidate frequency"]
    for r in metrics["raw"].get("candidates_by_symbol", [])[:20]:
        lines.append(f"- {r['symbol']}: {r['len']}")
    lines += [
        "",
        "## Recommendation",
        "Proceed to Sprint 04 only after PM verifies candidate density and no-lookahead tests; do not infer profitability here.",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(" ".join(f"{k}={v}" for k, v in metrics_flat.items() if not isinstance(v, list)))


if __name__ == "__main__":
    main()
