from __future__ import annotations

import hashlib
from dataclasses import dataclass

import polars as pl

from bybit_grid.research.range_features import ONE_MINUTE_MS


@dataclass(frozen=True)
class RegimeCoalesceConfig:
    cluster_bps: float = 25.0
    cluster_atr_fraction: float = 0.10
    min_tick_cluster_multiplier: float = 10.0
    max_gap_inside_regime_minutes: int = 5


def stable_range_regime_id(symbol: str, profile: str, cluster: str, first_ms: int) -> str:
    return hashlib.sha256(f"{symbol}|{profile}|{cluster}|{int(first_ms)}".encode()).hexdigest()[:32]


def add_actionable_cluster_id(raw: pl.DataFrame, cfg: RegimeCoalesceConfig | None = None) -> pl.DataFrame:
    cfg = cfg or RegimeCoalesceConfig()
    if raw.is_empty():
        return raw
    tick_expr = pl.col("tick_size") * cfg.min_tick_cluster_multiplier if "tick_size" in raw.columns else pl.lit(0.0)
    atr_expr = pl.col("atr_14").fill_null(0.0) * cfg.cluster_atr_fraction if "atr_14" in raw.columns else pl.lit(0.0)
    return (
        raw.with_columns(
            pl.max_horizontal(pl.col("current_close") * (cfg.cluster_bps / 10_000.0), atr_expr, tick_expr)
            .clip(lower_bound=1e-12)
            .alias("range_cluster_size")
        )
        .with_columns(
            (pl.col("range_low") / pl.col("range_cluster_size")).round(0).cast(pl.Int64).alias("range_low_cluster"),
            (pl.col("range_high") / pl.col("range_cluster_size")).round(0).cast(pl.Int64).alias("range_high_cluster"),
        )
        .with_columns(
            pl.concat_str([
                pl.col("range_low_cluster").cast(pl.Utf8),
                pl.lit(":"),
                pl.col("range_high_cluster").cast(pl.Utf8),
            ]).alias("range_cluster_id")
        )
    )


def coalesce_range_regimes(raw: pl.DataFrame, cfg: RegimeCoalesceConfig | None = None) -> pl.DataFrame:
    cfg = cfg or RegimeCoalesceConfig()
    if raw.is_empty():
        return pl.DataFrame()
    df = add_actionable_cluster_id(raw, cfg)
    if "raw_candidate_id" not in df.columns:
        df = df.with_columns(pl.col("candidate_id").alias("raw_candidate_id"))
    score_col = "range_quality_score" if "range_quality_score" in df.columns else "amplitude_score"
    rows: list[dict[str, object]] = []
    for key, part in df.sort(["symbol", "profile_name", "range_cluster_id", "signal_time_ms"]).group_by(
        ["symbol", "profile_name", "range_cluster_id"], maintain_order=True
    ):
        symbol, profile, cluster = key
        cur: list[dict[str, object]] = []
        last_ms: int | None = None
        for row in part.to_dicts():
            ts = int(row["signal_time_ms"])
            if last_ms is not None and ts - last_ms > cfg.max_gap_inside_regime_minutes * ONE_MINUTE_MS:
                rows.append(_regime_row(str(symbol), str(profile), str(cluster), cur, score_col))
                cur = []
            cur.append(row)
            last_ms = ts
        if cur:
            rows.append(_regime_row(str(symbol), str(profile), str(cluster), cur, score_col))
    return pl.DataFrame(rows).sort(["symbol", "profile_name", "first_seen_time_ms"])


def _regime_row(symbol: str, profile: str, cluster: str, rows: list[dict[str, object]], score_col: str) -> dict[str, object]:
    first_ms = int(min(r["signal_time_ms"] for r in rows))
    last_ms = int(max(r["signal_time_ms"] for r in rows))
    best = sorted(
        rows,
        key=lambda r: (
            -(float(r.get(score_col) or 0.0)),
            -int(r.get("midline_crosses") or 0),
            -int(r.get("lookback_minutes") or 0),
            int(r["signal_time_ms"]),
            str(r.get("raw_candidate_id") or r.get("candidate_id")),
        ),
    )[0]
    lookbacks = sorted({int(r["lookback_minutes"]) for r in rows})
    return {
        "range_regime_id": stable_range_regime_id(symbol, profile, cluster, first_ms),
        "symbol": symbol,
        "profile_name": profile,
        "range_cluster_id": cluster,
        "first_seen_time_ms": first_ms,
        "last_seen_time_ms": last_ms,
        "regime_duration_minutes": int((last_ms - first_ms) / ONE_MINUTE_MS) + 1,
        "raw_candidates_in_regime": len(rows),
        "lookbacks_observed": ",".join(map(str, lookbacks)),
        "lookback_min": min(lookbacks),
        "lookback_max": max(lookbacks),
        "range_low_median": float(pl.Series([r["range_low"] for r in rows]).median()),
        "range_high_median": float(pl.Series([r["range_high"] for r in rows]).median()),
        "range_mid_median": float(pl.Series([r["range_mid"] for r in rows]).median()),
        "best_score_in_regime": float(best.get(score_col) or 0.0),
        "best_raw_candidate_id": str(best.get("raw_candidate_id") or best.get("candidate_id")),
    }
