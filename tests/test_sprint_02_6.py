from pathlib import Path
import subprocess
import sys

import polars as pl

from bybit_grid.bybit.fgrid_constraints import parse_validate_response
from bybit_grid.bybit.fgrid_feasibility import summarize_min_investment, write_report
from bybit_grid.data.download_manifest import build_download_manifest


def test_feasibility_naming_and_target_margin_and_risk_proxy():
    row = parse_validate_response(
        {"symbol":"BTCUSDT","lastPrice":100,"min_price":95,"max_price":105,"stop_loss_price":90,"cell_number_requested":2,"leverage_requested":1},
        {"retCode":0,"result":{"check_code":"FGRID_CHECK_CODE_UNSPECIFIED","investment":{"from":"4","to":"100"},"cell_number":{"from":"2","to":"10"},"leverage":{"from":"1","to":"5"},"long_liq_price":"80","short_liq_price":"120","entry_price":{"from":"99","to":"101"},"take_profit_price":{"from":"106","to":"110"},"profit":{"from":"1","to":"2"}}},
    )
    assert row["min_investment_feasible_at_5usdt"] is True
    assert row["feasible_user_5usdt_rule"] is True
    assert row["target_init_margin_inside_validate_range"] is True
    assert row["long_liq_distance_from_last_pct"] == 20.0
    assert row["short_liq_distance_from_last_pct"] == 20.0
    assert row["entry_price_from"] == 99.0


def test_feasible_only_aggregate_excludes_zero_non_feasible():
    df=pl.DataFrame({"symbol":["A","B"],"investment_min":[0.0,4.0],"feasible_bybit":[False,True],"check_code":["ERR","FGRID_CHECK_CODE_UNSPECIFIED"]})
    _, agg = summarize_min_investment(df)
    assert agg["min_investment_min_global_all_rows"] == 0.0
    assert agg["min_investment_min_global_bybit_feasible_only"] == 4.0
    assert agg["symbols_min_investment_feasible_at_5"] == 1


def test_utf8_report_and_manifest_eligible_only(tmp_path: Path):
    report=tmp_path/'r.md'
    write_report(report, pl.DataFrame(), {"symbols_min_investment_feasible_at_5": 0})
    assert "PM warning" in report.read_text(encoding='utf-8')
    universe=pl.DataFrame({"symbol":["A","B"],"turnover24h":[2.0,1.0]})
    eligible=pl.DataFrame({"symbol":["A"],"min_investment_feasible_at_5usdt":[True]})
    manifest=build_download_manifest(universe, eligible, 1, 10, 1)
    assert manifest["symbol"].to_list() == ["A"]


def test_fast_download_flags_and_no_create_close_added():
    help_text = subprocess.run([sys.executable, "scripts/download_universe_data.py", "--help"], check=True, capture_output=True, text=True).stdout
    assert "--fast-max" in help_text and "--skip-existing-ok" in help_text
    files = list(Path("scripts").glob("*.py")) + list(Path("src").rglob("*.py"))
    text = "\n".join(p.read_text(encoding='utf-8') for p in files)
    assert "/v5/fgridbot/create" not in text.replace('bybit_fgrid_create_path: str = "/v5/fgridbot/create"','')
    assert "/v5/fgridbot/close" not in text.replace('bybit_fgrid_close_path: str = "/v5/fgridbot/close"','')
