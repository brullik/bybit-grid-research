from __future__ import annotations
import ast
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_HELPERS = {
    "_exercise",
    "dispatch_behavior",
    "run_behavior",
    "assert_behavior",
    "material_contract",
}
GENERIC_TEXT = (
    "production path exercises",
    "the contract returns the asserted success or stable failure",
    "placeholder",
    "constant-only",
)
CLI_SCRIPTS = {
    "scripts/import_bybit_public_review_pack_to_store.py",
    "scripts/audit_bybit_public_parquet_store.py",
    "scripts/plan_bybit_public_store_repairs.py",
    "scripts/make_bybit_public_parquet_seed_review_pack.py",
    "scripts/check_bybit_public_parquet_seed_review_pack.py",
}
REQUIRED_064A3 = tuple(
    """GOV-EXACT-ID-SET
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
CLI-FULL-LIFECYCLE-BYTICK-HOST""".splitlines()
)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _literal_strings(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and type(n.value) is str}


def _normalize_body(fn: ast.FunctionDef) -> str:
    clone = (
        ast.fix_missing_locations(
            ast.parse("\n".join(ast.get_source_segment("", n) or ast.dump(n) for n in fn.body))
        )
        if False
        else fn
    )
    for n in ast.walk(clone):
        for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset"):
            if hasattr(n, attr):
                setattr(n, attr, 0)
        if isinstance(n, ast.Constant) and type(n.value) is str and n.value in REQUIRED_064A3:
            n.value = "<BEHAVIOR_ID>"
    return ast.dump(clone, include_attributes=False)


def _resolve_test(nodeid: str):
    file_part, _, func_part = nodeid.partition("::")
    path = Path(file_part)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=file_part)
    fn_name = func_part.split("[")[0]
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == fn_name:
            return path, n
    raise ValueError("test_function_not_found")


def _symbol_present(fn: ast.FunctionDef, symbols: list[str]) -> bool:
    refs = {
        _call_name(n) for n in ast.walk(fn) if isinstance(n, (ast.Call, ast.Attribute, ast.Name))
    }
    suffixes = {s.split(".")[-1] for s in symbols}
    return bool(refs & set(symbols)) or bool(refs & suffixes)


def _ast_errors(row: dict, seen_bodies: dict[str, str]) -> list[str]:
    bid = row["behavior_id"]
    nodeid = row["nodeid"]
    errors = []
    try:
        _, fn = _resolve_test(nodeid)
    except Exception as e:
        return [f"missing_node_source:{nodeid}:{e}"]
    calls = [_call_name(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
    if any(c.split(".")[-1] in FORBIDDEN_HELPERS for c in calls):
        errors.append(f"generic_dispatcher_node:{nodeid}")
    top_calls = [n for n in fn.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(fn))
    has_raises_match = any(
        _call_name(n.func).endswith("pytest.raises") and any(k.arg == "match" for k in n.keywords)
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
    )
    if len(fn.body) <= 2 and len(top_calls) == 1 and not has_assert:
        errors.append(f"single_helper_no_assert:{nodeid}")
    strings = _literal_strings(fn)
    has_cli = "subprocess.run" in calls and bool(strings & CLI_SCRIPTS)
    has_market = any(
        "bybit_grid.data.market_store" in s for s in row["production_symbols"]
    ) and _symbol_present(fn, row["production_symbols"])
    if not (has_cli or has_market):
        errors.append(f"no_direct_production_call:{nodeid}")
    if not (has_assert or has_raises_match):
        errors.append(f"no_assertion_contract:{nodeid}")
    if not _symbol_present(fn, row["production_symbols"]):
        errors.append(f"production_symbol_not_referenced:{bid}")
    sig = _normalize_body(fn)
    if sig in seen_bodies:
        errors.append(f"duplicate_normalized_test_body:{nodeid}:{seen_bodies[sig]}")
    seen_bodies[sig] = nodeid
    return errors


def verify_required_behavior_json(path: Path, collected_nodes, *, ast_checks: bool = True):
    errors = []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"{path}:json_invalid:{e}"]
    if (
        set(raw) != {"schema", "behaviors"}
        or raw.get("schema") != "sprint_06_4a_3_required_behaviors_v1"
    ):
        errors.append(f"{path}:schema_invalid")
    rows = raw.get("behaviors")
    if type(rows) is not list:
        return errors + [f"{path}:behaviors_invalid"]
    bids = []
    seen_bodies = {}
    collected = set(collected_nodes)
    for i, row in enumerate(rows):
        if type(row) is not dict or set(row) != {
            "behavior_id",
            "nodeid",
            "production_symbols",
            "fixture",
            "mutation",
            "expected",
        }:
            errors.append(f"{path}:row_schema_invalid:{i}")
            continue
        bid = row["behavior_id"]
        bids.append(bid)
        if bid not in REQUIRED_064A3:
            errors.append(f"{path}:unknown_behavior_id:{bid}")
        if row["nodeid"] not in collected:
            errors.append(f"{path}:missing_node:{row['nodeid']}")
        if (
            type(row["production_symbols"]) is not list
            or not row["production_symbols"]
            or len(set(row["production_symbols"])) != len(row["production_symbols"])
        ):
            errors.append(f"{path}:production_symbols_invalid:{bid}")
        if any(type(row[k]) is not str or not row[k] for k in ("fixture", "mutation", "expected")):
            errors.append(f"{path}:traceability_text_invalid:{bid}")
        text = " ".join(str(row[k]).lower() for k in ("fixture", "mutation", "expected"))
        if any(t in text for t in GENERIC_TEXT):
            errors.append(f"{path}:generic_manifest_text:{bid}")
        if ast_checks and row["nodeid"] in collected:
            errors.extend(f"{path}:{e}" for e in _ast_errors(row, seen_bodies))
    if tuple(bids) != REQUIRED_064A3:
        errors.append(f"{path}:exact_behavior_id_set_invalid")
    for x in sorted({b for b in bids if bids.count(b) > 1}):
        errors.append(f"{path}:duplicate_behavior_id:{x}")
    return errors


@dataclass(frozen=True)
class CoverageMapResult:
    ok: bool
    errors: tuple[str, ...]
    counts: dict[str, int]

    def to_json(self):
        return json.dumps(
            {
                "ok": self.ok,
                "required_064a3_count": len(REQUIRED_064A3),
                "mapped_material_nodes": self.counts.get("mapped_material_nodes", 0),
                "generic_dispatcher_nodes": self.counts.get("generic_dispatcher_nodes", 0),
                "duplicate_normalized_test_bodies": self.counts.get(
                    "duplicate_normalized_test_bodies", 0
                ),
                "errors": list(self.errors),
            },
            sort_keys=True,
            separators=(",", ":"),
        )


def verify_maps(map_specs, collected_nodes):
    errors = []
    if map_specs:
        line_re = re.compile(
            r"^\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*$"
        )
        for path_text, expected in map_specs:
            rows = []
            for line in Path(path_text).read_text(encoding="utf-8").splitlines():
                m = line_re.match(line)
                if m and not m.group(1).lower().startswith("behavior"):
                    rows.append(
                        (
                            m.group(1).strip(),
                            m.group(2).strip(),
                            m.group(3).strip(),
                            m.group(4).strip(),
                            m.group(5).strip(),
                        )
                    )
            if len(rows) != expected:
                errors.append(f"{path_text}:count:{len(rows)}!={expected}")
            seen = {}
            for bid, node, fixture, mutation, expected_text in rows:
                node_low = node.lower()
                if (
                    "behavior_coverage_material_nodes" in node_low
                    or "material_contract" in node_low
                ):
                    errors.append(f"{path_text}:forbidden_noop_node:{node}")
                if node not in collected_nodes:
                    errors.append(f"{path_text}:missing_node:{node}")
                if expected_text.strip() == bid.strip():
                    errors.append(f"{path_text}:expected_repeats_behavior_id:{bid}")
                sig = (fixture.lower(), mutation.lower(), expected_text.lower())
                if sig in seen and seen[sig] != node:
                    errors.append(f"{path_text}:duplicate_material_mapping:{bid}:{seen[sig]}")
                seen[sig] = node
        return CoverageMapResult(
            False if errors else True,
            tuple(errors),
            {
                "mapped_material_nodes": 0,
                "generic_dispatcher_nodes": 0,
                "duplicate_normalized_test_bodies": 0,
            },
        )
    req = Path("docs/sprint_06_4a_3_required_behaviors.json")
    if req.exists():
        errors.extend(verify_required_behavior_json(req, collected_nodes))
    generic = sum("generic_dispatcher_node" in e for e in errors)
    return CoverageMapResult(
        not errors,
        tuple(errors),
        {
            "mapped_material_nodes": 0 if errors else len(REQUIRED_064A3),
            "generic_dispatcher_nodes": generic,
            "duplicate_normalized_test_bodies": sum(
                "duplicate_normalized_test_body" in e for e in errors
            ),
        },
    )


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
