
import polars as pl
import pytest

from bybit_grid.bybit.fgrid_constraints import append_constraints, parse_validate_response, write_redacted_response
from bybit_grid.data.download_manifest import build_download_manifest
from bybit_grid.universe.builder import filter_universe, normalize_universe


def _inst(symbol, quote='USDT', status='Trading', pre=False, turnover='1'):
    return {'symbol': symbol, 'baseCoin': symbol.replace(quote,''), 'quoteCoin': quote, 'status': status, 'contractType': 'LinearPerpetual', 'isPreListing': pre, 'launchTime': '1000', 'priceFilter': {'tickSize':'0.1'}, 'lotSizeFilter': {'qtyStep':'1','minOrderQty':'1','minNotionalValue':'5'}, 'leverageFilter': {'maxLeverage':'10'}, 'fundingInterval': 480}


def test_universe_filter_excludes_prelaunch_and_non_usdt():
    df = normalize_universe([_inst('AAAUSDT'), _inst('BBBUSDT', pre=True), _inst('CCCUSDC', quote='USDC')], [{'symbol':'AAAUSDT','turnover24h':'10000000','volume24h':'1','lastPrice':'1'}, {'symbol':'BBBUSDT','turnover24h':'10000000','lastPrice':'1'}])
    cand, sel, counts = filter_universe(df, 5_000_000, 10)
    assert cand['symbol'].to_list() == ['AAAUSDT']
    assert sel['symbol'].to_list() == ['AAAUSDT']
    assert counts['excluded_prelaunch_count'] == 1


def test_universe_rank_by_turnover():
    df = normalize_universe([_inst('AUSDT'), _inst('BUSDT')], [{'symbol':'AUSDT','turnover24h':'10','lastPrice':'1'}, {'symbol':'BUSDT','turnover24h':'20','lastPrice':'1'}])
    _, sel, _ = filter_universe(df, 0, 10)
    assert sel['symbol'].to_list() == ['BUSDT', 'AUSDT']
    assert sel.filter(pl.col('symbol') == 'BUSDT')['liquidity_rank'][0] == 1


def test_fgrid_constraint_parser_extracts_ranges_and_5usdt_rule():
    meta={'symbol':'XUSDT','lastPrice':1.0,'tickSize':'0.1','range_width_pct':0.02,'min_price':0.9,'max_price':1.1,'stop_loss_price':0.8,'cell_number_requested':5,'leverage_requested':2,'init_margin_requested':5.0}
    resp={'retCode':0,'retMsg':'OK','result':{'investment':{'from':'4','to':'100'},'cell_number':{'from':'2','to':'10'},'leverage':{'from':'1','to':'5'}}}
    row=parse_validate_response(meta, resp)
    assert row['investment_min'] == 4.0 and row['investment_max'] == 100.0
    assert row['cell_number_min'] == 2.0 and row['cell_number_max'] == 10.0
    assert row['leverage_min'] == 1.0 and row['leverage_max'] == 5.0
    assert row['feasible_bybit'] is True
    assert row['feasible_user_5usdt_rule'] is True


def test_5usdt_feasibility_blocks_missing_or_high_investment():
    meta={'symbol':'XUSDT','lastPrice':1.0,'tickSize':'0.1','range_width_pct':0.02,'min_price':0.9,'max_price':1.1,'stop_loss_price':0.8,'cell_number_requested':5,'leverage_requested':2,'init_margin_requested':5.0}
    high=parse_validate_response(meta, {'retCode':0,'result':{'investment':{'from':'6'},'cell_number':{'from':'2','to':'10'},'leverage':{'from':'1','to':'5'}}})
    miss=parse_validate_response(meta, {'retCode':0,'result':{'cell_number':{'from':'2','to':'10'},'leverage':{'from':'1','to':'5'}}})
    assert high['feasible_user_5usdt_rule'] is False
    assert miss['blocker_reason'] == 'investment_min_missing'


def test_validate_batch_resume_dedupes(tmp_path):
    path=tmp_path/'constraints.parquet'
    row={'symbol':'A','range_width_pct':0.02,'cell_number_requested':2,'leverage_requested':1,'init_margin_requested':5,'feasible_user_5usdt_rule':False}
    append_constraints(path,[row])
    append_constraints(path,[{**row,'feasible_user_5usdt_rule':True}])
    df=pl.read_parquet(path)
    assert df.height == 1 and df['feasible_user_5usdt_rule'][0] is True


def test_download_manifest_respects_launch_time_and_size_cap():
    uni=pl.DataFrame({'symbol':['AUSDT'],'turnover24h':[10.0],'launchTime':[32503680000000]})
    df=build_download_manifest(uni, pl.DataFrame(), 90, 1, 25)
    assert df['start_ms'][0] == 32503680000000
    with pytest.raises(ValueError):
        build_download_manifest(pl.DataFrame({'symbol':['AUSDT'],'turnover24h':[10.0],'launchTime':[0]}), pl.DataFrame(), 90, 1, 0.000001)


def test_no_private_output_contains_secrets_or_balances(tmp_path):
    p=tmp_path/'raw.json'
    write_redacted_response(p, {'apiKey':'k','secret':'s','signature':'sig','result': {'symbol':'BTCUSDT'}})
    txt=p.read_text().lower()
    assert '"k"' not in txt and '"s"' not in txt and '"sig"' not in txt

# RED probe: strict API response envelope implementation intentionally unavailable.
