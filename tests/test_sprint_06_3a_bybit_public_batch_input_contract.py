from decimal import Decimal
import pytest

from bybit_grid.backtest.ohlc_replay.evidence import build_contract_audit, derive_scenario_audit
from bybit_grid.data.public_batch.models import InclusiveMinuteWindow, BybitInstrumentMeta, PublicBatchError
from bybit_grid.data.public_batch.parsers import parse_server_time, parse_trade_kline_page, parse_instrument_page
from bybit_grid.data.public_batch.pagination import plan_1m_windows


def test_missing_and_empty_reproducibility_audit_fail_closed():
    audit = derive_scenario_audit()
    assert build_contract_audit(audit, None)["contract_audit_ok"] is False
    assert build_contract_audit(audit, {})["contract_audit_ok"] is False
    assert build_contract_audit(audit, {"reproducibility_audit_ok": True})["canonical_byte_identity_enforced_bool"] is True


def test_server_time_cutoff_is_bybit_server_time():
    st = parse_server_time({"retCode": 0, "time": 120123, "result": {"timeNano": "120123000000", "timeSecond": "120"}})
    assert st.server_time_ms == 120123
    assert st.last_closed_open_time_ms == 60000


def test_bool_as_int_float_symbol_and_missing_nested_fields_rejected():
    with pytest.raises(PublicBatchError):
        InclusiveMinuteWindow(True, 60000)
    w = InclusiveMinuteWindow(0, 0)
    raw = {"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT", "list": [["0", 1.0, "2", "1", "1", "0", "0"]]}}
    with pytest.raises(PublicBatchError):
        parse_trade_kline_page(raw, "linear", "BTCUSDT", w, 0)
    inst = {"retCode": 0, "result": {"category": "linear", "list": [{"symbol": " btcusdt "}]}}
    with pytest.raises((PublicBatchError, KeyError)):
        parse_instrument_page(inst, "linear", 0)


def test_kline_reverse_normalizes_and_rejects_duplicate_out_of_window_unclosed():
    w = InclusiveMinuteWindow(0, 60000)
    raw = {"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT", "list": [["60000", "1", "2", "1", "2", "0", "0"], ["0", "1", "1", "1", "1", "0", "0"]]}}
    rows = parse_trade_kline_page(raw, "linear", "BTCUSDT", w, 60000)
    assert [r.open_time_ms for r in rows] == [0, 60000]
    dup = {"retCode": 0, "result": {"category": "linear", "symbol": "BTCUSDT", "list": [["0", "1", "1", "1", "1", "0", "0"], ["0", "1", "1", "1", "1", "0", "0"]]}}
    with pytest.raises(PublicBatchError):
        parse_trade_kline_page(dup, "linear", "BTCUSDT", w, 60000)
    with pytest.raises(PublicBatchError):
        parse_trade_kline_page(raw, "linear", "BTCUSDT", w, 0)


def test_plan_1000_1001_boundary():
    one = plan_1m_windows(0, 999 * 60000)
    two = plan_1m_windows(0, 1000 * 60000)
    assert [(x.start_open_time_ms, x.end_open_time_ms, x.row_count) for x in one] == [(0, 999 * 60000, 1000)]
    assert [(x.start_open_time_ms, x.end_open_time_ms, x.row_count) for x in two] == [(0, 999 * 60000, 1000), (1000 * 60000, 1000 * 60000, 1)]


def test_instrument_funding_intervals_not_assumed_eight_hours():
    for interval in (60, 240, 480):
        m = BybitInstrumentMeta("linear", "BTCUSDT", "LinearPerpetual", "Trading", "BTC", "USDT", "USDT", 0, 0, False, interval, Decimal("0.1"), Decimal("0.001"), Decimal("0.001"), Decimal("5"), Decimal("1"), Decimal("100"), Decimal("0.01"), 0)
        assert m.funding_interval_minutes == interval
        assert m.eligible_for_replay()


def test_smoke_script_imports_without_network():
    import scripts.smoke_bybit_public_batch_contract as smoke
    assert hasattr(smoke, "main")
