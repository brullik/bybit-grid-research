from __future__ import annotations

from pathlib import Path

import polars as pl

THRESHOLDS = (5, 10, 25, 50, 100, 250, 500)
UNSPECIFIED = "FGRID_CHECK_CODE_UNSPECIFIED"


def _feasible_rows(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty() or "investment_min" not in df.columns:
        return pl.DataFrame()
    out = df.filter(pl.col("investment_min").is_not_null())
    if "feasible_bybit" in out.columns:
        out = out.filter(pl.col("feasible_bybit"))
    if "check_code" in out.columns:
        out = out.filter(pl.col("check_code").is_null() | (pl.col("check_code") == UNSPECIFIED))
    return out


def summarize_min_investment(df: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, object]]:
    if df.is_empty():
        return pl.DataFrame(), {"symbols_tested": 0, "configs_tested": 0}
    all_valid = df.filter(pl.col("investment_min").is_not_null())
    bybit_valid = _feasible_rows(df)
    rows = []
    for key, part in df.partition_by("symbol", as_dict=True).items():
        symbol = key[0] if isinstance(key, tuple) else key
        vp = _feasible_rows(part)
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
            "target_init_margin_inside_validate_range": best.get("target_init_margin_inside_validate_range"),
            "bybit_feasible_config_count": vp.height,
        }
        for t in THRESHOLDS:
            count = vp.filter(pl.col("investment_min") <= t).height if not vp.is_empty() else 0
            row[f"min_investment_{t}usdt_feasible_config_count"] = count
            row[f"user_{t}usdt_feasible_config_count"] = count
        rows.append(row)
    out = pl.DataFrame(rows).sort("min_investment_min_seen", nulls_last=True)
    median_val = out["min_investment_min_seen"].drop_nulls().median() if not out.is_empty() else None
    five_valid = bybit_valid.filter(pl.col("investment_min") <= 5) if not bybit_valid.is_empty() else bybit_valid
    agg = {
        "symbols_tested": df["symbol"].unique().len(),
        "configs_tested": df.height,
        "min_investment_min_global_all_rows": float(all_valid["investment_min"].min()) if not all_valid.is_empty() else None,
        "min_investment_min_global_bybit_feasible_only": float(bybit_valid["investment_min"].min()) if not bybit_valid.is_empty() else None,
        "min_investment_min_global_5usdt_feasible_only": float(five_valid["investment_min"].min()) if not five_valid.is_empty() else None,
        "min_investment_min_global": float(bybit_valid["investment_min"].min()) if not bybit_valid.is_empty() else None,
        "min_investment_median_by_symbol": float(median_val) if median_val is not None else None,
    }
    for t in THRESHOLDS:
        val = out.filter(pl.col(f"min_investment_{t}usdt_feasible_config_count") > 0).height
        agg[f"symbols_min_investment_feasible_at_{t}"] = val
        agg[f"symbols_feasible_at_{t}"] = val
    return out, agg


def write_report(path: Path, summary: pl.DataFrame, aggregate: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Sprint 02 Native Grid Feasibility Report", "",
        "**PM warning:** This report verifies Bybit minimum investment constraints only. It does not prove that realized loss to SL is <= 5 USDT. Risk-budget validation starts in Sprint 03/Backtest.", "",
        "## Aggregate counts", "",
    ]
    for k, v in aggregate.items():
        if not k.startswith("symbols_feasible_at_"):
            lines.append(f"- {k}: {v}")
    lines += ["", "## By symbol", ""]
    if summary.is_empty():
        lines.append("No validation rows.")
    else:
        cols = summary.columns
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in summary.to_dicts():
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
