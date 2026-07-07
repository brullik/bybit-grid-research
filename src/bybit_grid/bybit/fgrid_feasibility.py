from __future__ import annotations

from pathlib import Path

import polars as pl

THRESHOLDS = (5, 10, 25, 50, 100, 250, 500)


def summarize_min_investment(df: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, object]]:
    if df.is_empty():
        return pl.DataFrame(), {"symbols_tested": 0, "configs_tested": 0}
    valid = df.filter(pl.col("investment_min").is_not_null())
    rows = []
    for key, part in df.partition_by("symbol", as_dict=True).items():
        symbol = key[0] if isinstance(key, tuple) else key
        vp = part.filter(pl.col("investment_min").is_not_null())
        if vp.is_empty():
            best = part.head(1).to_dicts()[0]
            min_inv = median = p90 = None
        else:
            best = vp.sort("investment_min").head(1).to_dicts()[0]
            min_inv = float(vp["investment_min"].min())
            median = float(vp["investment_min"].median())
            p90 = float(vp.select(pl.col("investment_min").quantile(0.9)).item())
        row = {
            "symbol": symbol,
            "min_investment_min_seen": min_inv,
            "median_investment_min": median,
            "p90_investment_min": p90,
            "best_config_for_min_investment": f"width={best.get('range_width_pct')} cells={best.get('cell_number_requested')} lev={best.get('leverage_requested')} margin={best.get('init_margin_requested')} sl={best.get('stop_loss_mult')}",
            "min_range_width_pct": best.get("range_width_pct"),
            "best_cell_number": best.get("cell_number_requested"),
            "best_leverage": best.get("leverage_requested"),
            "best_stop_loss_mult": best.get("stop_loss_mult"),
            "bybit_feasible_config_count": part.filter(pl.col("feasible_bybit")).height
            if "feasible_bybit" in part.columns
            else 0,
        }
        for t in THRESHOLDS:
            row[f"user_{t}usdt_feasible_config_count"] = (
                vp.filter((pl.col("feasible_bybit")) & (pl.col("investment_min") <= t)).height
                if "feasible_bybit" in vp.columns
                else 0
            )
        rows.append(row)
    out = pl.DataFrame(rows).sort("min_investment_min_seen", nulls_last=True)
    agg = {
        "symbols_tested": df["symbol"].unique().len(),
        "configs_tested": df.height,
        "min_investment_min_global": float(valid["investment_min"].min())
        if not valid.is_empty()
        else None,
        "min_investment_median_by_symbol": float(out["min_investment_min_seen"].median())
        if not out.is_empty()
        else None,
    }
    for t in THRESHOLDS:
        agg[f"symbols_feasible_at_{t}"] = out.filter(
            pl.col(f"user_{t}usdt_feasible_config_count") > 0
        ).height
    return out, agg


def write_report(path: Path, summary: pl.DataFrame, aggregate: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Sprint 02 Native Grid Feasibility Report", "", "## Aggregate counts", ""]
    for k, v in aggregate.items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## PM decision evidence",
        "",
        "- Decision A: Native Bybit FGrid under 5 USDT is feasible.",
        "- Decision B: Native Bybit FGrid under 5 USDT is not feasible, but feasible at X USDT.",
        "- Decision C: Native Bybit FGrid is not suitable for 500 USDT startup; consider custom grid later.",
        "",
        "## By symbol",
        "",
    ]
    if summary.is_empty():
        lines.append("No validation rows.")
    else:
        cols = summary.columns
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in summary.to_dicts():
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
