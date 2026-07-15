from types import MappingProxyType
from bybit_grid.data.market_store.canonical import canonical_json_bytes
from bybit_grid.data.market_store.models import StoreRoundTripAudit


def test_canonical_mappingproxy_dataclass_serializes():
    b = canonical_json_bytes(StoreRoundTripAudit(True, (), MappingProxyType({"a":"b"})))
    assert b == b'{"dataset_hashes":{"a":"b"},"failures":[],"ok":true}\n'
