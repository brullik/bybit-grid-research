from __future__ import annotations
import hashlib
import zipfile
from pathlib import Path
from bybit_grid.data.market_store.import_public_batch import load_validated_public_replay_batch_from_review_pack, import_validated_public_batch_to_store
from bybit_grid.data.market_store.inventory import snapshot_tree
from bybit_grid.data.market_store.models import StoreFileInventoryEntry

RUN_ID = "synthetic_public_batch_064a33"
SYMBOL = "BTCUSDT"
END = 1704067200000
SERVER_TIME_MS = END + 60000 + 12345


def build_synthetic_public_review_pack(tmp_path: Path, *, base_url: str) -> Path:
    path = Path(tmp_path) / ("synthetic_public_review_pack_" + hashlib.sha256(base_url.encode()).hexdigest()[:8] + ".zip")
    # The full public-batch semantic builder is intentionally not networked in this helper; tests that need
    # production validation can replace this archive with recorded public-batch fixtures.
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("capture_plan.json", '{"base_url":"' + base_url + '","run_id":"' + RUN_ID + '"}\n')
        z.writestr("public_batch_run_status.json", '{"status":"complete"}\n')
        z.writestr("recorded_public_responses.jsonl", b"")
    return path


def load_synthetic_validated_evidence(tmp_path: Path, *, base_url: str):
    pack = build_synthetic_public_review_pack(tmp_path, base_url=base_url)
    return load_validated_public_replay_batch_from_review_pack(pack, expected_run_id=RUN_ID)


def import_synthetic_store(tmp_path: Path, *, base_url: str):
    evidence = load_synthetic_validated_evidence(tmp_path, base_url=base_url)
    store = Path(tmp_path) / "store"
    receipt = import_validated_public_batch_to_store(evidence, store)
    return store, receipt, evidence


def mutate_zip_and_rehash(source: Path, destination: Path, *, member: str, mutator) -> Path:
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zout:
        for name in zin.namelist():
            data = zin.read(name)
            if name == member:
                data = mutator(data)
            zout.writestr(name, data)
    return destination

__all__ = ["build_synthetic_public_review_pack", "load_synthetic_validated_evidence", "import_synthetic_store", "snapshot_tree", "mutate_zip_and_rehash", "StoreFileInventoryEntry"]
