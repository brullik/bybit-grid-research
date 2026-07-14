from __future__ import annotations
import json
import re
import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDERS = (
    "placeholder",
    "test_sprint_06_4a_contract_matrix.py",
    "test_accepted_lifecycle_behavior",
    "behavior-specific",
    "requirement ",
)
LINE_RE = re.compile(
    r"^\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*$"
)


@dataclass(frozen=True)
class CoverageMapResult:
    ok: bool
    errors: tuple[str, ...]
    counts: dict[str, int]

    def to_json(self):
        return json.dumps(
            {"counts": self.counts, "errors": list(self.errors), "ok": self.ok},
            sort_keys=True,
            separators=(",", ":"),
        )


def parse_map(path: Path):
    rows = []
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        m = LINE_RE.match(line)
        if m and not m.group(1).lower().startswith("behavior"):
            rows.append(
                {
                    "behavior_id": m.group(1).strip(),
                    "nodeid": m.group(2).strip(),
                    "fixture": m.group(3).strip(),
                    "mutation": m.group(4).strip(),
                    "expected": m.group(5).strip(),
                    "line": i,
                }
            )
    if not rows:
        # legacy numbered lines
        for i, line in enumerate(text.splitlines(), 1):
            nm = re.search(r"Node: `([^`]+)`", line)
            if nm:
                rows.append(
                    {
                        "behavior_id": str(len(rows) + 1),
                        "nodeid": nm.group(1),
                        "fixture": line,
                        "mutation": line,
                        "expected": line,
                        "line": i,
                    }
                )
    return rows, text


def verify_maps(map_specs, collected_nodes):
    collected = set(collected_nodes)
    errors = []
    counts = {}
    for path, expected in map_specs:
        rows, text = parse_map(Path(path))
        counts[str(path)] = len(rows)
        low = text.lower()
        for ph in PLACEHOLDERS:
            if ph in low:
                errors.append(f"{path}:placeholder_phrase:{ph}")
        if len(rows) != expected:
            errors.append(f"{path}:count:{len(rows)}!={expected}")
        bids = [r["behavior_id"] for r in rows]
        nodes = [r["nodeid"] for r in rows]
        for x in sorted({b for b in bids if bids.count(b) > 1}):
            errors.append(f"{path}:duplicate_behavior_id:{x}")
        for x in sorted({n for n in nodes if nodes.count(n) > 1}):
            errors.append(f"{path}:duplicate_nodeid:{x}")
        for r in rows:
            if r["nodeid"] not in collected:
                errors.append(f"{path}:missing_node:{r['nodeid']}")
            if not (r["fixture"] and r["mutation"] and r["expected"]):
                errors.append(f"{path}:incomplete_row:{r['behavior_id']}")
    return CoverageMapResult(not errors, tuple(errors), counts)


def collect_nodes(command: str):
    cp = subprocess.run(
        shlex.split(command),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if cp.returncode not in (0, 5):
        raise RuntimeError(cp.stdout)
    return [
        ln.strip()
        for ln in cp.stdout.splitlines()
        if "::" in ln and not ln.startswith("<")
    ]
