from __future__ import annotations
import json
import re
import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path

PLACEHOLDERS = (
    "placeholder",
    "material_contract",
    "binds to an executable node",
    "validates collected closure row",
    'fixture = {"id"',
    'assert fixture["id"]',
    "assert index >= 0",
    "test_sprint_06_4a_contract_matrix.py",
    "test_accepted_lifecycle_behavior",
    "behavior-specific",
    "requirement ",
)

REQUIRED_064A3 = tuple("""GOV-EXACT-ID-SET
GOV-MISSING-NODE
GOV-NOOP-REJECTED
CLI-HELP-ALL
CLI-MISSING-ARGS-ALL
DECIMAL-MAX-BOUNDARY
DECIMAL-MIN-BOUNDARY
DECIMAL-ROUNDING-REJECTED
PLAN-INSTRUMENT-SNAPSHOT
PLAN-KLINE-CROSS-MONTH
PLAN-FUNDING-FOUR-MONTHS
PLAN-MULTI-SYMBOL-REJECTED
PREFLIGHT-INVALID-ROW-ZERO-WRITES
PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES
PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES
CHUNK-EARLY-CLEANUP
CHUNK-MID-CLEANUP
CHUNK-LATE-CLEANUP
CHUNK-CANONICAL-MANIFEST
CHUNK-ACTUAL-PATH-MATCH
CHUNK-PK-SCHEMA-MATCH
CHUNK-EXISTING-CORRUPTION-REJECTED
IMPORT-SYNTHETIC-REAL-SHAPE
IMPORT-SOURCE-BYTES-IMMUTABLE
IMPORT-RECEIPT-LAST
IMPORT-NOOP-TYPED
IMPORT-NOOP-ZERO-MUTATION
IMPORT-NOOP-CORRUPT-CHUNK-REJECTED
IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED
AUDIT-EMPTY-REJECTED
AUDIT-VERSION-TAMPER-REJECTED
AUDIT-ORPHAN-CHUNK-REJECTED
AUDIT-ORPHAN-EVIDENCE-REJECTED
AUDIT-RECEIPT-TAMPER-REJECTED
AUDIT-GLOBAL-DUPLICATE-REJECTED
AUDIT-GLOBAL-CONFLICT-REJECTED
AUDIT-UNEXPECTED-ENTRY-REJECTED
AUDIT-STALE-STAGING-REJECTED
REPLAY-SNAPSHOT-REQUIRED
REPLAY-SNAPSHOT-ROW-RETURNED
REPLAY-COMPLETE-TRADE-MARK
REPLAY-FUNDING-MARK-JOIN
REPLAY-MISSING-MARK-JOIN-REJECTED
COVERAGE-STRICT-INPUTS
COVERAGE-OUT-OF-WINDOW-REJECTED
COVERAGE-GAP-WINDOWS
RESUME-INCLUSIVE-1000
RESUME-MONTH-YEAR-LEAP
FUNDING-STRICT-TIMESTAMPS
DUCKDB-FOUR-VIEWS
DUCKDB-DECIMAL-TYPES
DUCKDB-CONNECTION-CLOSED
PACK-BUILDER-BAD-STORE-REJECTED
PACK-EXACT-MEMBER-SET
PACK-EMPTY-MANIFEST-REJECTED
PACK-REHASHED-FAKE-REJECTED
PACK-NESTED-EVIDENCE-VALIDATED
PACK-REPORT-TAMPER-REJECTED
PACK-TEMP-CLEANUP
CLI-FULL-LIFECYCLE-BYBIT-HOST
CLI-FULL-LIFECYCLE-BYTICK-HOST""".splitlines())


def verify_required_behavior_json(path: Path, collected_nodes):
    errors = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"{path}:json_invalid:{e}"]
    if set(raw) != {"schema", "behaviors"} or raw.get("schema") != "sprint_06_4a_3_required_behaviors_v1":
        errors.append(f"{path}:schema_invalid")
    rows = raw.get("behaviors")
    if type(rows) is not list:
        return errors + [f"{path}:behaviors_invalid"]
    bids = []
    collected = set(collected_nodes)
    for i, row in enumerate(rows):
        if type(row) is not dict or set(row) != {"behavior_id", "nodeid", "material", "expected"}:
            errors.append(f"{path}:row_schema_invalid:{i}")
            continue
        bid = row["behavior_id"]
        bids.append(bid)
        if bid not in REQUIRED_064A3:
            errors.append(f"{path}:unknown_behavior_id:{bid}")
        node = row["nodeid"]
        if node not in collected:
            errors.append(f"{path}:missing_node:{node}")
        text = (row["material"] + " " + row["expected"]).lower()
        if any(p in text for p in PLACEHOLDERS) or "constant-only" in text:
            errors.append(f"{path}:forbidden_noop_pattern:{bid}")
    if tuple(bids) != REQUIRED_064A3:
        errors.append(f"{path}:exact_behavior_id_set_invalid")
    for x in sorted({b for b in bids if bids.count(b) > 1}):
        errors.append(f"{path}:duplicate_behavior_id:{x}")
    for x in sorted(set(REQUIRED_064A3) - set(bids)):
        errors.append(f"{path}:missing_behavior_id:{x}")
    return errors

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
        seen_material = {}
        for r in rows:
            node_low = r["nodeid"].lower()
            if "behavior_coverage_material_nodes" in node_low or "material_contract" in node_low:
                errors.append(f"{path}:forbidden_noop_node:{r['nodeid']}")
            if r["nodeid"] not in collected:
                errors.append(f"{path}:missing_node:{r['nodeid']}")
            if not (r["fixture"] and r["mutation"] and r["expected"]):
                errors.append(f"{path}:incomplete_row:{r['behavior_id']}")
            if r["expected"].strip() == r["behavior_id"].strip():
                errors.append(f"{path}:expected_repeats_behavior_id:{r['behavior_id']}")
            generic = (r["fixture"] + " " + r["mutation"]).lower()
            if (
                "deterministic in-process fixture" in generic
                or "behavior identifier" in generic
                or "generic" in generic
            ):
                errors.append(f"{path}:generic_fixture_or_mutation:{r['behavior_id']}")
            sig = (r["fixture"].lower(), r["mutation"].lower(), r["expected"].lower())
            if sig in seen_material and seen_material[sig] != r["nodeid"]:
                errors.append(
                    f"{path}:duplicate_material_mapping:{r['behavior_id']}:{seen_material[sig]}"
                )
            seen_material[sig] = r["nodeid"]
    req = Path("docs/sprint_06_4a_3_required_behaviors.json")
    if req.exists():
        req_errors = verify_required_behavior_json(req, collected)
        errors.extend(req_errors)
        counts[str(req)] = len(REQUIRED_064A3) if not req_errors else -1
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
    return [ln.strip() for ln in cp.stdout.splitlines() if "::" in ln and not ln.startswith("<")]
