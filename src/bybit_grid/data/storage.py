from datetime import datetime, timezone
from pathlib import Path
import polars as pl


def utc_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def ts_label(dt: datetime | None = None) -> str:
    return (dt or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")


def metadata_path(data_dir: Path, name: str) -> Path:
    return data_dir / "metadata" / name


def kline_partition_path(data_dir: Path, dataset: str, symbol: str, open_time_ms: int) -> Path:
    dt = datetime.fromtimestamp(open_time_ms / 1000, tz=timezone.utc)
    return (
        data_dir
        / "raw"
        / dataset
        / f"symbol={symbol}"
        / f"year={dt.year:04d}"
        / f"month={dt.month:02d}"
        / "part.parquet"
    )


def funding_partition_path(data_dir: Path, symbol: str, timestamp_ms: int) -> Path:
    dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    return (
        data_dir / "raw" / "funding" / f"symbol={symbol}" / f"year={dt.year:04d}" / "part.parquet"
    )


def write_parquet_merge(path: Path, df: pl.DataFrame, unique: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        df = pl.concat([pl.read_parquet(path), df], how="diagonal_relaxed")
    if unique:
        df = df.unique(subset=unique, keep="last").sort(unique)
    df.write_parquet(path)
