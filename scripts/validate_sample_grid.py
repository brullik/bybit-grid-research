import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.bybit.client import BybitClient
from bybit_grid.config import load_settings
from bybit_grid.logging import redacted_json_dump, setup_logging
from bybit_grid.reporting import utc_now_iso, write_sprint_report

REQUIRED = {"category", "symbol", "lowerPrice", "upperPrice", "gridNum", "investment"}


def sample_payload(symbol: str) -> dict[str, object]:
    return {
        "sampleOnly": True,
        "category": "linear",
        "symbol": symbol,
        "lowerPrice": "50000",
        "upperPrice": "80000",
        "gridNum": 10,
        "investment": "100",
    }


parser = argparse.ArgumentParser()
parser.add_argument("--symbol", default="BTCUSDT")
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()
settings = load_settings()
setup_logging(settings.log_level)
started_at = utc_now_iso()
payload = sample_payload(args.symbol)
missing = REQUIRED - payload.keys()
if missing:
    raise SystemExit(f"refusing to send validate request; missing fields: {sorted(missing)}")
out = settings.data_dir / "metadata" / "grid_validate_redacted.json"
out.parent.mkdir(parents=True, exist_ok=True)
if args.dry_run:
    result = {"dry_run": True, "payload": payload, "network_request": False}
    out.write_text(redacted_json_dump(result), encoding="utf-8")
    write_sprint_report(
        settings.data_dir,
        {
            "command": "validate_sample_grid --dry-run",
            "started_at": started_at,
            "ended_at": utc_now_iso(),
            "status": "dry-run",
            "output_paths": [str(out)],
            "grid validate status": "dry-run; no network request",
        },
    )
    print(redacted_json_dump(result))
    raise SystemExit(0)
if not settings.grid_validate_enabled:
    result = {"skipped": True, "reason": "GRID_VALIDATE_ENABLED is false"}
else:
    with BybitClient(settings) as client:
        result = client.validate_grid_bot(payload, runtime_live=False)
out.write_text(redacted_json_dump(result), encoding="utf-8")
write_sprint_report(
    settings.data_dir,
    {
        "command": "validate_sample_grid",
        "started_at": started_at,
        "ended_at": utc_now_iso(),
        "status": "ok" if not result.get("skipped") else "skipped",
        "output_paths": [str(out)],
        "grid validate status": result,
    },
)
print("ok validate-only handled")
