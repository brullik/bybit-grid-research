from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any



@dataclass(frozen=True)
class FeeRate:
    symbol: str
    maker_fee_rate: float
    taker_fee_rate: float
    fee_snapshot_id: str
    fee_source: str


@dataclass(frozen=True)
class CostScenario:
    name: str
    entry_fee_source: str
    exit_fee_source: str
    sl_exit_fee_source: str
    slippage_bps_per_market_leg: float = 0.0


def load_cost_config(path: str | Path) -> dict[str, Any]:
    # Minimal parser for the versioned Sprint 05 scenario file; avoids adding a
    # runtime dependency solely for this small, fixed schema.
    text = Path(path).read_text(encoding="utf-8")
    data: dict[str, Any] = {"scenarios": {}}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line == "scenarios:":
            continue
        if line.startswith("cost_model_version:"):
            data["cost_model_version"] = line.split(":", 1)[1].strip()
        elif line.startswith("fee_snapshot_id:"):
            data["fee_snapshot_id"] = line.split(":", 1)[1].strip()
        elif line.startswith("fee_source:"):
            data["fee_source"] = line.split(":", 1)[1].strip()
        elif ":" in line and "{" in line and "}" in line:
            name, rest = line.split(":", 1)
            inner = rest[rest.index("{") + 1 : rest.rindex("}")]
            values: dict[str, Any] = {}
            for item in inner.split(","):
                key, value = item.split(":", 1)
                v = value.strip()
                values[key.strip()] = float(v) if v.replace(".", "", 1).isdigit() else v
            data["scenarios"][name.strip()] = values
    if data.get("cost_model_version") != "cost_v1":
        raise ValueError("cost_model_version must be cost_v1")
    scenarios = data.get("scenarios") or {}
    required = {"maker_maker", "maker_taker", "taker_taker", "stress_taker_plus_slippage"}
    missing = required - set(scenarios)
    if missing:
        raise ValueError(f"missing cost scenarios: {sorted(missing)}")
    return data


def scenario_objects(config: dict[str, Any]) -> list[CostScenario]:
    return [CostScenario(name=name, **values) for name, values in (config.get("scenarios") or {}).items()]
