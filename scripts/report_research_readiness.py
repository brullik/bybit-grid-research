from __future__ import annotations

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl


def main() -> None:
    eligible = pl.read_parquet('data/processed/research_eligible_universe.parquet') if Path('data/processed/research_eligible_universe.parquet').exists() else pl.DataFrame()
    quality = pl.read_parquet('data/processed/universe_quality_summary.parquet') if Path('data/processed/universe_quality_summary.parquet').exists() else pl.DataFrame()
    manifest = pl.read_parquet('data/processed/research_download_manifest.parquet') if Path('data/processed/research_download_manifest.parquet').exists() else pl.DataFrame()
    def rate(dataset: str) -> float:
        if manifest.is_empty():
            return 0.0
        if quality.is_empty():
            return 0.0
        q=quality.filter((pl.col('dataset')==dataset) & (pl.col('rows')>0))
        return q['symbol'].unique().len()/max(1, manifest.height)*100
    gap = int(quality['missing_gaps'].sum()) if (not quality.is_empty() and 'missing_gaps' in quality.columns) else 0
    dup = int(quality['duplicate_candles'].sum()) if (not quality.is_empty() and 'duplicate_candles' in quality.columns) else 0
    bad = int(quality['bad_ohlc'].sum()) if (not quality.is_empty() and 'bad_ohlc' in quality.columns) else 0
    zero = int(quality['zero_volume_rows'].sum()) if (not quality.is_empty() and 'zero_volume_rows' in quality.columns) else 0
    disk_gb = float(quality['disk_bytes'].sum()/1_000_000_000) if (not quality.is_empty() and 'disk_bytes' in quality.columns) else 0.0
    downloaded = quality['symbol'].unique().len() if not quality.is_empty() and 'symbol' in quality.columns else 0
    ready = downloaded if dup == 0 and bad == 0 else 0
    recommendation = 'pass' if eligible.height >= 30 and rate('klines') >= 98 and rate('mark_klines') >= 95 and dup == 0 and bad == 0 else 'fail'
    metrics = {
        'eligible_symbols_count': eligible.height,
        'downloaded_symbols_count': downloaded,
        'normal_kline_success_rate': round(rate('klines'), 3),
        'mark_kline_success_rate': round(rate('mark_klines'), 3),
        'funding_success_rate': round(rate('funding'), 3),
        'gap_count_total': gap,
        'duplicate_count_total': dup,
        'bad_ohlc_count_total': bad,
        'zero_volume_rows_total': zero,
        'disk_usage_gb': round(disk_gb, 6),
        'symbols_ready_for_sprint_03': ready,
        'symbols_excluded_quality': max(0, downloaded-ready),
        'recommendation': recommendation,
    }
    Path('reports').mkdir(exist_ok=True)
    lines=['# Sprint 02 Research Readiness Report','']+[f'- {k}: {v}' for k,v in metrics.items()]
    Path('reports/sprint_02_research_readiness_report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(' '.join(f'{k}={v}' for k,v in metrics.items()))
if __name__ == '__main__':
    main()
