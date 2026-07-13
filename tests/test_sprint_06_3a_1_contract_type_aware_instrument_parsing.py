from decimal import Decimal
import importlib
import json
import pytest

from bybit_grid.data.public_batch.audit import audit_instrument_universe
from bybit_grid.data.public_batch.models import BybitServerTime, PublicBatchError
from bybit_grid.data.public_batch.pagination import fetch_all_instruments
from bybit_grid.data.public_batch.parsers import parse_instrument_page
import scripts.smoke_bybit_public_batch_contract as smoke


def item(symbol, contract="LinearPerpetual", funding=480, quote="USDT", settle="USDT", tick="0.1"):
    return {
        "symbol": symbol,
        "contractType": contract,
        "status": "Trading",
        "baseCoin": symbol[:3],
        "quoteCoin": quote,
        "settleCoin": settle,
        "launchTime": "0",
        "deliveryTime": "0",
        "isPreListing": False,
        "fundingInterval": funding,
        "priceFilter": {"tickSize": tick},
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
        "leverageFilter": {"minLeverage": "1", "maxLeverage": "100", "leverageStep": "0.01"},
    }


def page(items, cursor=""):
    return {"retCode": 0, "result": {"category": "linear", "list": items, "nextPageCursor": cursor}}


def test_perpetual_futures_usdc_parse_order_decimals_and_replay_eligibility():
    rows, _ = parse_instrument_page(
        page([
            item("BTCUSDT", funding=480, tick="0.5"),
            item("BTCUSDTZ26", contract="LinearFutures", funding=0),
            item("ETHUSDC", funding=480, quote="USDC", settle="USDC"),
        ]),
        "linear",
        123,
    )
    assert [r.symbol for r in rows] == ["BTCUSDT", "BTCUSDTZ26", "ETHUSDC"]
    assert rows[0].tick_size == Decimal("0.5")
    assert rows[0].eligible_for_replay()
    assert not rows[1].eligible_for_replay()
    assert rows[1].funding_interval_minutes == 0
    assert not rows[2].eligible_for_replay()


def test_zero_funding_usdt_perpetual_parses_without_default_and_fails_audit():
    rows, _ = parse_instrument_page(page([item("ZEROUSDT", funding=0)]), "linear", 0)
    assert rows[0].funding_interval_minutes == 0
    assert not rows[0].eligible_for_replay()
    audit = audit_instrument_universe(rows)
    assert not audit.universe_audit_ok
    assert audit.replay_candidate_zero_funding_interval_symbols == ("ZEROUSDT",)
    assert audit.failures == ("replay_candidate_zero_funding_interval",)


@pytest.mark.parametrize("funding", [-1, "-1"])
def test_negative_funding_interval_rejected(funding):
    with pytest.raises(PublicBatchError):
        parse_instrument_page(page([item("BADUSDT", funding=funding)]), "linear", 0)


@pytest.mark.parametrize("funding", [True, False, 1.5, "", "abc"])
def test_non_exact_funding_interval_tokens_rejected(funding):
    with pytest.raises(PublicBatchError):
        parse_instrument_page(page([item("BADUSDT", funding=funding)]), "linear", 0)


def test_unknown_contract_type_rejected():
    with pytest.raises(PublicBatchError):
        parse_instrument_page(page([item("BADUSDT", contract="InversePerpetual")]), "linear", 0)


class Client:
    def __init__(self):
        self.calls = []

    def public_get(self, path, params):
        self.calls.append((path, dict(params)))
        if len(self.calls) == 1:
            return page([item("BTCUSDT")], "NEXT")
        return page([item("BTCUSDTZ26", contract="LinearFutures", funding=0)])


def test_fetch_all_instruments_explicit_status_cursor_two_page_zero_futures():
    c = Client()
    st = BybitServerTime(120000, 120, 120000000000, 120000, 60000)
    rows, audits = fetch_all_instruments(c, st)
    assert c.calls == [
        ("/v5/market/instruments-info", {"category": "linear", "status": "Trading", "limit": 1000}),
        (
            "/v5/market/instruments-info",
            {"category": "linear", "status": "Trading", "limit": 1000, "cursor": "NEXT"},
        ),
    ]
    assert [r.symbol for r in rows] == ["BTCUSDT", "BTCUSDTZ26"]
    assert len(audits) == 2


def test_universe_audit_counts_are_deterministic_and_futures_zero_does_not_fail():
    rows, _ = parse_instrument_page(
        page([item("BTCUSDT"), item("ETHUSDC", quote="USDC", settle="USDC"), item("BTCUSDTZ26", contract="LinearFutures", funding=0)]),
        "linear",
        0,
    )
    audit = audit_instrument_universe(rows)
    assert audit.universe_audit_ok
    assert dict(audit.contract_type_counts) == {"LinearFutures": 1, "LinearPerpetual": 2}
    assert dict(audit.funding_interval_counts) == {"0": 1, "480": 2}
    assert audit.zero_funding_interval_symbols == ("BTCUSDTZ26",)
    assert dict(audit.zero_funding_interval_by_contract_type) == {"LinearFutures": 1}
    assert audit.linear_perpetual_count == 2
    assert audit.linear_futures_count == 1
    assert audit.usdt_linear_perpetual_count == 1
    assert audit.replay_eligible_count == 1


def test_universe_audit_duplicate_and_non_model_failures():
    row = parse_instrument_page(page([item("BTCUSDT")]), "linear", 0)[0][0]
    audit = audit_instrument_universe((row, row, object()))
    assert not audit.universe_audit_ok
    assert "symbols_unique_bool" in audit.failures
    assert "all_rows_exact_public_models_bool" in audit.failures


def test_smoke_json_helpers_canonical_and_no_credentials(tmp_path):
    out = tmp_path / "smoke.json"
    exc = RuntimeError("boom")
    payload = smoke._failure("server_time", exc)
    text = smoke._canonical_write(out, payload)
    assert text == json.dumps(payload, sort_keys=True, separators=(",", ":"))
    loaded = json.loads(out.read_text())
    assert loaded["status"] == "failed"
    assert loaded["contains_credentials"] is False
    assert "api" not in out.read_text().lower()


def test_smoke_import_safe_and_no_private_live_surface(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("network on import")

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fail)
    mod = importlib.reload(smoke)
    assert hasattr(mod, "main")
    assert "api_key" not in open(smoke.__file__, encoding="utf-8").read().lower()
    assert "/v5/order" not in open(smoke.__file__, encoding="utf-8").read()
