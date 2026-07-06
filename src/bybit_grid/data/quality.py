import polars as pl
from bybit_grid.data.storage import ts_label

def detect_1m_gaps(df: pl.DataFrame, symbol_col='symbol', time_col='open_time_ms') -> pl.DataFrame:
    reports=[]
    if df.is_empty(): return pl.DataFrame({'symbol':[],'start_ms':[],'end_ms':[],'missing_minutes':[]})
    for sym, part in df.sort([symbol_col,time_col]).partition_by(symbol_col, as_dict=True).items():
        vals=part[time_col].to_list(); seen=set(vals)
        for prev, cur in zip(vals, vals[1:]):
            if cur-prev>60_000:
                reports.append({'symbol': sym[0] if isinstance(sym, tuple) else sym, 'start_ms': prev+60_000, 'end_ms': cur-60_000, 'missing_minutes': (cur-prev)//60_000-1})
    return pl.DataFrame(reports) if reports else pl.DataFrame({'symbol':[],'start_ms':[],'end_ms':[],'missing_minutes':[]})

def save_gap_report(data_dir, df: pl.DataFrame) -> pl.DataFrame:
    report=detect_1m_gaps(df); path=data_dir/'quality'/f'gap_report_{ts_label()}.parquet'; path.parent.mkdir(parents=True, exist_ok=True); report.write_parquet(path); return report
