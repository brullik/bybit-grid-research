from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from typing import Literal

from bybit_grid.data.market_store.import_public_batch import (
    load_validated_public_replay_batch_from_review_pack,
    import_validated_public_batch_to_store,
)
from bybit_grid.data.market_store.inventory import snapshot_tree
from bybit_grid.data.market_store.models import StoreFileInventoryEntry
from bybit_grid.data.public_batch.evidence import CANONICAL_MEMBERS
from bybit_grid.data.public_batch.recording import RecordingPublicClient
from scripts import make_bybit_public_batch_review_pack as builder
from scripts import run_bybit_public_batch_evidence as runner

SYNTHETIC_RUN_ID_BYBIT = "synthetic_public_batch_064a34_bybit"
SYNTHETIC_RUN_ID_BYTICK = "synthetic_public_batch_064a34_bytick"
SYMBOL = "BTCUSDT"
KLINE_ROW_COUNT = 1001
FUNDING_ROW_COUNT = 300
INSTRUMENT_ROW_COUNT = 721
END = 1_704_067_200_000
MINUTE = 60_000
FUNDING_INTERVAL = 8 * 60
SERVER_TIME_MS = END + MINUTE


@dataclass(frozen=True)
class SyntheticPublicPack:
    path: Path
    bytes: bytes
    sha256: str
    run_id: str
    base_url: str
    symbol: str
    server_time_ms: int
    snapshot_server_time_ms: int
    window_start_ms: int
    window_end_ms: int
    expected_instrument_count: int
    expected_trade_count: int
    expected_mark_count: int
    expected_funding_count: int
    expected_funding_observation_count: int


class Response:
    status = 200
    headers = {"content-type": "application/json; charset=utf-8"}

    def __init__(self, payload):
        self._body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    def getcode(self):
        return self.status

    def read(self):
        return self._body

    def close(self):
        pass


def _instrument(symbol):
    return {
        "symbol": symbol,
        "contractType": "LinearPerpetual",
        "status": "Trading",
        "baseCoin": symbol[:-4],
        "quoteCoin": "USDT",
        "settleCoin": "USDT",
        "launchTime": "0",
        "deliveryTime": "0",
        "isPreListing": False,
        "fundingInterval": str(FUNDING_INTERVAL),
        "priceFilter": {"tickSize": "0.1"},
        "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001", "minNotionalValue": "5"},
        "leverageFilter": {"minLeverage": "1", "maxLeverage": "100", "leverageStep": "0.01"},
    }


INSTRUMENTS = [_instrument(SYMBOL)] + [
    _instrument(f"COIN{i:03d}USDT") for i in range(1, INSTRUMENT_ROW_COUNT)
]
FUNDING_START = END - 120 * 24 * 60 * MINUTE
FUNDING_TIMES = [FUNDING_START + i * FUNDING_INTERVAL * MINUTE for i in range(FUNDING_ROW_COUNT)]


def synthetic_client(base_url):
    def opener(req, timeout=30):
        parsed = urlparse(req.full_url)
        endpoint = parsed.path
        q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if endpoint == "/v5/market/time":
            return Response(
                {
                    "retCode": 0,
                    "result": {
                        "timeNano": str(SERVER_TIME_MS * 1_000_000),
                        "timeSecond": str(SERVER_TIME_MS // 1000),
                    },
                    "time": SERVER_TIME_MS,
                }
            )
        if endpoint == "/v5/market/instruments-info":
            limit = int(q["limit"])
            start = int(q.get("cursor") or 0)
            rows = INSTRUMENTS[start : start + limit]
            nextc = str(start + limit) if start + limit < len(INSTRUMENTS) else ""
            return Response(
                {
                    "retCode": 0,
                    "result": {"category": "linear", "list": rows, "nextPageCursor": nextc},
                }
            )
        if endpoint in {"/v5/market/kline", "/v5/market/mark-price-kline"}:
            start = int(q["start"])
            end = int(q["end"])
            mark = endpoint.endswith("mark-price-kline")
            rows = []
            for t in range(start, end + 1, MINUTE):
                base = "50000.0" if mark else "50001.0"
                rows.append(
                    [str(t), base, base, base, base]
                    if mark
                    else [str(t), base, base, base, base, "1.0", "50000.0"]
                )
            return Response(
                {"retCode": 0, "result": {"category": "linear", "symbol": SYMBOL, "list": rows}}
            )
        if endpoint == "/v5/market/funding/history":
            start = int(q["startTime"])
            end = int(q["endTime"])
            limit = int(q["limit"])
            times = [t for t in FUNDING_TIMES if start <= t <= end][-limit:]
            return Response(
                {
                    "retCode": 0,
                    "result": {
                        "list": [
                            {
                                "symbol": SYMBOL,
                                "fundingRateTimestamp": str(t),
                                "fundingRate": "0.0001",
                            }
                            for t in times
                        ]
                    },
                }
            )
        raise AssertionError(endpoint)

    return RecordingPublicClient(
        base_url=base_url, opener=opener, max_attempts=1, timeout_seconds=30
    )


def _run_id(base_url: str) -> str:
    return (
        SYNTHETIC_RUN_ID_BYBIT if base_url == "https://api.bybit.com" else SYNTHETIC_RUN_ID_BYTICK
    )


def build_synthetic_public_review_pack(
    tmp_path: Path, *, base_url: Literal["https://api.bybit.com", "https://api.bytick.com"]
) -> SyntheticPublicPack:
    run_id = _run_id(base_url)
    root = Path(tmp_path) / "public_runs"
    out = Path(tmp_path) / f"{run_id}.zip"
    args = SimpleNamespace(
        run_id=run_id,
        symbol=SYMBOL,
        kline_row_count=KLINE_ROW_COUNT,
        funding_lookback_days=100,
        output_root=str(root),
        base_url=base_url,
        timeout_seconds=30,
    )
    runner._run(args, client=synthetic_client(base_url))
    assert builder.main(["--run-id", run_id, "--input-root", str(root), "--output", str(out)]) == 0
    b = out.read_bytes()
    with zipfile.ZipFile(out) as z:
        assert z.namelist() == list(CANONICAL_MEMBERS)
    return SyntheticPublicPack(
        out,
        b,
        hashlib.sha256(b).hexdigest(),
        run_id,
        base_url,
        SYMBOL,
        SERVER_TIME_MS,
        SERVER_TIME_MS,
        END - (KLINE_ROW_COUNT - 1) * MINUTE,
        END,
        INSTRUMENT_ROW_COUNT,
        KLINE_ROW_COUNT,
        KLINE_ROW_COUNT,
        FUNDING_ROW_COUNT,
        2,
    )


def load_synthetic_validated_evidence(tmp_path: Path, *, base_url: str):
    pack = build_synthetic_public_review_pack(tmp_path, base_url=base_url)  # type: ignore[arg-type]
    return load_validated_public_replay_batch_from_review_pack(
        pack.path, expected_run_id=pack.run_id
    )


def import_synthetic_store(tmp_path: Path, *, base_url: str):
    evidence = load_synthetic_validated_evidence(tmp_path, base_url=base_url)
    store = Path(tmp_path) / "store"
    receipt = import_validated_public_batch_to_store(evidence, store)
    return store, receipt, evidence


def mutate_zip_and_rehash(source: Path, destination: Path, *, member: str, mutator) -> Path:
    with (
        zipfile.ZipFile(source) as zin,
        zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for name in zin.namelist():
            data = zin.read(name)
            if name == member:
                data = mutator(data)
            zout.writestr(name, data)
    return destination


__all__ = [
    "SyntheticPublicPack",
    "build_synthetic_public_review_pack",
    "load_synthetic_validated_evidence",
    "import_synthetic_store",
    "snapshot_tree",
    "mutate_zip_and_rehash",
    "StoreFileInventoryEntry",
]
