import zipfile
import pytest
from bybit_grid.common.source_tree import build_source_tree_manifest
from bybit_grid.data.market_store.evidence import check_seed_review_pack
from bybit_grid.data.market_store.models import MarketStoreError


def test_source_tree_manifest_deterministic(tmp_path):
    (tmp_path / "a.py").write_text("x=1\r\n")
    assert build_source_tree_manifest(tmp_path) == build_source_tree_manifest(tmp_path)


def test_unsafe_zip_path_rejected(tmp_path):
    z = tmp_path / "bad.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../evil", "x")
        f.writestr("review_pack_manifest.json", '{"members":{}}')
    with pytest.raises(MarketStoreError):
        check_seed_review_pack(z)
