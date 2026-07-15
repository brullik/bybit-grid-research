import zipfile

import pytest
from bybit_grid.data.market_store.evidence import check_seed_review_pack
from bybit_grid.data.market_store.models import MarketStoreError
from bybit_grid.data.market_store.canonical import canonical_json_bytes


def test_portable_empty_manifest_rejected(tmp_path):
    z = tmp_path/"p.zip"
    with zipfile.ZipFile(z,"w") as f:
        f.writestr("review_pack_manifest.json", canonical_json_bytes({"members": {}}))
    with pytest.raises(MarketStoreError, match="empty_manifest"):
        check_seed_review_pack(z)
