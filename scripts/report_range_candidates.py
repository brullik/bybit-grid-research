from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl
from bybit_grid.research.range_candidate_summary import build_summary, read_candidates


def resolve_run(run_id: str) -> str:
    if run_id == "latest":
        p = Path("data/processed/range_runs/latest_run.txt")
        if not p.exists():
            raise SystemExit("latest range run pointer not found")
        return p.read_text(encoding="utf-8").strip()
    return run_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="latest")
    args = ap.parse_args()
    run_id = resolve_run(args.run_id)
    root = Path("data/processed/range_runs") / run_id
    raw = read_candidates(root / "raw_candidates")
    event = read_candidates(root / "event_candidates")
    actionable = read_candidates(root / "actionable_events")
    rej_path = root / "summary" / "range_rejection_summary.parquet"
    rej = pl.read_parquet(rej_path) if rej_path.exists() else pl.DataFrame()
    flat = {"run_id": run_id, "raw_candidates_total": raw.height, "event_candidates_total": event.height, "actionable_events_total": actionable.height}
    flat.update({f"raw_{k}": v for k, v in build_summary(raw).items() if not isinstance(v, list)})
    flat.update({f"event_{k}": v for k, v in build_summary(event).items() if not isinstance(v, list)})
    flat.update({f"actionable_{k}": v for k, v in build_summary(actionable).items() if not isinstance(v, list)})
    if not actionable.is_empty() and "range_action_event_id" in actionable.columns:
        flat["duplicate_action_event_id_count"] = actionable.height - actionable["range_action_event_id"].n_unique()
    if not rej.is_empty():
        for c in rej.columns:
            if c.endswith("_count") or c in {"total_window_positions", "raw_candidate_pass_count"}:
                flat[c] = int(rej[c].sum())
    out = Path(f"reports/sprint_03_2_range_actionable_report_{run_id}.md")
    out.parent.mkdir(exist_ok=True)
    lines = ["# Sprint 03.2 Range Candidate Report", ""] + [f"- {k}: {v}" for k, v in flat.items()] + ["", "## Recommendation", "Use actionable_events only for Gate 3 density review; do not proceed to outcomes unless density gates pass."]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(" ".join(f"{k}={v}" for k, v in flat.items()))


if __name__ == "__main__":
    main()
