from __future__ import annotations

import hashlib
from dataclasses import dataclass

import polars as pl

from bybit_grid.research.range_features import ONE_MINUTE_MS


@dataclass(frozen=True)
class CoalesceConfig:
    event_mode: str = "rising_edge_cooldown"
    cooldown_mode: str = "lookback_fraction"
    cooldown_minutes: int | None = None
    range_cluster_bps: float = 5.0


def stable_event_id(symbol: str, profile_name: str, lookback_minutes: int, cluster_id: str, first_seen_time_ms: int) -> str:
    payload = f"{symbol}|{profile_name}|{lookback_minutes}|{cluster_id}|{first_seen_time_ms}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def _cooldown(lb: int, cfg: CoalesceConfig) -> int:
    if cfg.cooldown_mode == "none":
        return 0
    if cfg.cooldown_mode == "fixed":
        return int(cfg.cooldown_minutes or 0)
    return int(min(lb / 4, 120))


def coalesce_range_events(raw: pl.DataFrame, cfg: CoalesceConfig | None = None) -> pl.DataFrame:
    cfg = cfg or CoalesceConfig()
    if raw.is_empty():
        return raw
    df = raw.sort(["symbol", "profile_name", "lookback_minutes", "signal_time_ms"])
    if "raw_candidate_id" not in df.columns:
        df = df.with_columns(pl.col("candidate_id").alias("raw_candidate_id"))
    bps = float(cfg.range_cluster_bps) / 10_000.0
    df = df.with_columns(
        pl.max_horizontal(
            pl.col("current_close") * bps,
            pl.when(pl.col("tick_size").is_not_null()).then(pl.col("tick_size") * 5).otherwise(0)
            if "tick_size" in df.columns
            else pl.lit(0),
        ).alias("range_cluster_size")
    ).with_columns(
        (pl.col("range_low") / pl.col("range_cluster_size")).round(0).cast(pl.Int64).alias("range_low_cluster"),
        (pl.col("range_high") / pl.col("range_cluster_size")).round(0).cast(pl.Int64).alias("range_high_cluster"),
    ).with_columns(
        pl.concat_str([
            pl.col("range_low_cluster").cast(pl.Utf8), pl.lit(":"), pl.col("range_high_cluster").cast(pl.Utf8)
        ]).alias("range_cluster_id")
    )
    rows: list[dict[str, object]] = []
    for key, part in df.group_by(["symbol", "profile_name", "lookback_minutes", "range_cluster_id"], maintain_order=True):
        symbol, profile, lb, cluster_id = key
        cooldown = _cooldown(int(lb), cfg)
        last_event_ms: int | None = None
        cluster_rows = part.to_dicts()
        for idx, row in enumerate(cluster_rows):
            ts = int(row["signal_time_ms"])
            prev_equiv = idx > 0 and ts - int(cluster_rows[idx - 1]["signal_time_ms"]) == ONE_MINUTE_MS
            in_cd = last_event_ms is not None and ts - last_event_ms < cooldown * ONE_MINUTE_MS
            if prev_equiv or in_cd:
                continue
            following = [r for r in cluster_rows[idx:] if int(r["signal_time_ms"]) >= ts]
            contiguous = []
            expected = ts
            for r in following:
                if int(r["signal_time_ms"]) != expected:
                    break
                contiguous.append(r)
                expected += ONE_MINUTE_MS
            out = dict(row)
            last_seen = int(contiguous[-1]["signal_time_ms"] if contiguous else ts)
            out.update(
                {
                    "raw_candidate_id": row.get("raw_candidate_id") or row.get("candidate_id"),
                    "range_event_id": stable_event_id(str(symbol), str(profile), int(lb), str(cluster_id), ts),
                    "range_cluster_id": str(cluster_id),
                    "event_mode": cfg.event_mode if cooldown else "rising_edge",
                    "cooldown_minutes": cooldown,
                    "raw_candidates_in_cluster": len(contiguous) or 1,
                    "first_seen_time_ms": ts,
                    "last_seen_time_ms": last_seen,
                    "cluster_duration_minutes": int((last_seen - ts) / ONE_MINUTE_MS) + 1,
                }
            )
            rows.append(out)
            last_event_ms = ts
    return pl.DataFrame(rows).sort(["symbol", "profile_name", "lookback_minutes", "signal_time_ms"])
