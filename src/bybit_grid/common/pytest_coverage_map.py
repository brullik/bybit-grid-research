from __future__ import annotations
import ast
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

FORBIDDEN_HELPERS = {
    "_exercise",
    "dispatch_behavior",
    "run_behavior",
    "assert_behavior",
    "material_contract",
}
GENERIC_TEXT = (
    "production path exercises",
    "the contract returns",
    "specific deterministic fixture",
    "specific material mutation",
    "exact stable assertion",
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


REQUIRED_PRODUCTION_SYMBOLS_064A35: Mapping[str, tuple[str, ...]] = {
    "GOV-EXACT-ID-SET": ('verify_required_behavior_json',),
    "GOV-MISSING-NODE": ('verify_required_behavior_json',),
    "GOV-NOOP-REJECTED": ('verify_required_behavior_json',),
    "CLI-HELP-ALL": ('subprocess.run',),
    "CLI-MISSING-ARGS-ALL": ('subprocess.run',),
    "DECIMAL-MAX-BOUNDARY": ('ensure_decimal128_38_18',),
    "DECIMAL-MIN-BOUNDARY": ('ensure_decimal128_38_18',),
    "DECIMAL-ROUNDING-REJECTED": ('ensure_decimal128_38_18',),
    "PLAN-INSTRUMENT-SNAPSHOT": ('partition_validated_rows',),
    "PLAN-KLINE-CROSS-MONTH": ('partition_validated_rows',),
    "PLAN-FUNDING-FOUR-MONTHS": ('partition_validated_rows',),
    "PLAN-MULTI-SYMBOL-REJECTED": ('partition_validated_rows',),
    "PREFLIGHT-INVALID-ROW-ZERO-WRITES": ('build_import_preflight_plan', 'snapshot_tree',),
    "PREFLIGHT-INCOMING-DUPLICATE-ZERO-WRITES": ('build_import_preflight_plan', 'snapshot_tree',),
    "PREFLIGHT-COMMITTED-CONFLICT-ZERO-WRITES": ('build_import_preflight_plan', 'snapshot_tree',),
    "CHUNK-EARLY-CLEANUP": ('write_chunk_atomic', 'snapshot_tree',),
    "CHUNK-MID-CLEANUP": ('write_chunk_atomic', 'snapshot_tree',),
    "CHUNK-LATE-CLEANUP": ('write_chunk_atomic', 'snapshot_tree',),
    "CHUNK-CANONICAL-MANIFEST": ('write_chunk_atomic', 'read_and_validate_chunk',),
    "CHUNK-ACTUAL-PATH-MATCH": ('write_chunk_atomic', 'read_and_validate_chunk',),
    "CHUNK-PK-SCHEMA-MATCH": ('write_chunk_atomic', 'read_and_validate_chunk',),
    "CHUNK-EXISTING-CORRUPTION-REJECTED": ('write_chunk_atomic', 'read_and_validate_chunk',),
    "IMPORT-SYNTHETIC-REAL-SHAPE": ('import_validated_public_batch_to_store',),
    "IMPORT-SOURCE-BYTES-IMMUTABLE": ('import_validated_public_batch_to_store',),
    "IMPORT-RECEIPT-LAST": ('import_validated_public_batch_to_store',),
    "IMPORT-NOOP-TYPED": ('import_validated_public_batch_to_store',),
    "IMPORT-NOOP-ZERO-MUTATION": ('import_validated_public_batch_to_store',),
    "IMPORT-NOOP-CORRUPT-CHUNK-REJECTED": ('import_validated_public_batch_to_store',),
    "IMPORT-NOOP-CORRUPT-EVIDENCE-REJECTED": ('import_validated_public_batch_to_store',),
    "AUDIT-EMPTY-REJECTED": ('audit_market_store',),
    "AUDIT-VERSION-TAMPER-REJECTED": ('audit_market_store',),
    "AUDIT-ORPHAN-CHUNK-REJECTED": ('audit_market_store',),
    "AUDIT-ORPHAN-EVIDENCE-REJECTED": ('audit_market_store',),
    "AUDIT-RECEIPT-TAMPER-REJECTED": ('audit_market_store',),
    "AUDIT-GLOBAL-DUPLICATE-REJECTED": ('audit_market_store',),
    "AUDIT-GLOBAL-CONFLICT-REJECTED": ('audit_market_store',),
    "AUDIT-UNEXPECTED-ENTRY-REJECTED": ('audit_market_store',),
    "AUDIT-STALE-STAGING-REJECTED": ('audit_market_store',),
    "REPLAY-SNAPSHOT-REQUIRED": ('read_replay_slice',),
    "REPLAY-SNAPSHOT-ROW-RETURNED": ('read_replay_slice',),
    "REPLAY-COMPLETE-TRADE-MARK": ('read_replay_slice',),
    "REPLAY-FUNDING-MARK-JOIN": ('read_replay_slice',),
    "REPLAY-MISSING-MARK-JOIN-REJECTED": ('read_replay_slice',),
    "COVERAGE-STRICT-INPUTS": ('scan_minute_coverage',),
    "COVERAGE-OUT-OF-WINDOW-REJECTED": ('scan_minute_coverage',),
    "COVERAGE-GAP-WINDOWS": ('scan_minute_coverage',),
    "RESUME-INCLUSIVE-1000": ('plan_bounded_resume_windows',),
    "RESUME-MONTH-YEAR-LEAP": ('plan_bounded_resume_windows',),
    "FUNDING-STRICT-TIMESTAMPS": ('scan_funding_observed_range',),
    "DUCKDB-FOUR-VIEWS": ('open_readonly_duckdb_views', 'duckdb_smoke_audit',),
    "DUCKDB-DECIMAL-TYPES": ('open_readonly_duckdb_views', 'duckdb_smoke_audit',),
    "DUCKDB-CONNECTION-CLOSED": ('open_readonly_duckdb_views', 'duckdb_smoke_audit',),
    "PACK-BUILDER-BAD-STORE-REJECTED": ('make_seed_review_pack', 'check_seed_review_pack',),
    "PACK-EXACT-MEMBER-SET": ('make_seed_review_pack', 'check_seed_review_pack',),
    "PACK-EMPTY-MANIFEST-REJECTED": ('make_seed_review_pack', 'check_seed_review_pack',),
    "PACK-REHASHED-FAKE-REJECTED": ('make_seed_review_pack', 'check_seed_review_pack',),
    "PACK-NESTED-EVIDENCE-VALIDATED": ('make_seed_review_pack', 'check_seed_review_pack',),
    "PACK-REPORT-TAMPER-REJECTED": ('make_seed_review_pack', 'check_seed_review_pack',),
    "PACK-TEMP-CLEANUP": ('make_seed_review_pack', 'check_seed_review_pack',),
    "CLI-FULL-LIFECYCLE-BYBIT-HOST": ('subprocess.run',),
    "CLI-FULL-LIFECYCLE-BYTICK-HOST": ('subprocess.run',),
}

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
    clone = ast.fix_missing_locations(ast.parse(ast.unparse(fn))).body[0]
    for n in ast.walk(clone):
        for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset"):
            if hasattr(n, attr):
                setattr(n, attr, 0)
        if isinstance(n, ast.Constant):
            if type(n.value) in (str, int, float):
                if type(n.value) is str and n.value in REQUIRED_064A3:
                    n.value = "<BEHAVIOR_ID>"
                else:
                    n.value = "<CONST>"
    return ast.dump(clone, include_attributes=False)


def _called_symbols(fn: ast.FunctionDef) -> set[str]:
    return {_call_name(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}


def _symbol_called(fn: ast.FunctionDef, symbols) -> bool:
    calls = _called_symbols(fn)
    suffixes = {s.split(".")[-1] for s in symbols}
    return bool(calls & set(symbols)) or bool({c.split(".")[-1] for c in calls} & suffixes)


def _assert_is_constant_only(node: ast.Assert) -> bool:
    return all(isinstance(n, (ast.Assert, ast.Compare, ast.Constant, ast.GtE, ast.Load)) for n in ast.walk(node))

def _resolve_test(nodeid: str):
    file_part, _, func_part = nodeid.partition("::")
    path = Path(file_part)
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=file_part)
    fn_name = func_part.split("[")[0]
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name == fn_name:
            return path, n
    raise ValueError("test_function_not_found")



def _ast_errors(row: dict, seen_bodies: dict[str, str]) -> list[str]:
    bid = row["behavior_id"]
    nodeid = row["nodeid"]
    errors = []
    try:
        _, fn = _resolve_test(nodeid)
    except Exception as e:
        return [f"missing_node_source:{nodeid}:{e}"]
    calls = list(_called_symbols(fn))
    if any(c.split(".")[-1] in FORBIDDEN_HELPERS for c in calls):
        errors.append(f"generic_dispatcher_node:{nodeid}")
    top_calls = [n for n in fn.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)]
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    has_assert = bool(asserts)
    has_raises_match = any(
        _call_name(n.func).endswith("pytest.raises") and any(k.arg == "match" for k in n.keywords)
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
    )
    if len(fn.body) <= 2 and len(top_calls) == 1 and not has_assert:
        errors.append(f"single_helper_no_assert:{nodeid}")
    strings = _literal_strings(fn)
    has_cli = "subprocess.run" in calls and bool(strings & CLI_SCRIPTS)
    has_required_call = _symbol_called(fn, row["production_symbols"])
    if not (has_cli or has_required_call):
        errors.append(f"no_direct_production_call:{nodeid}")
    if not (has_assert or has_raises_match):
        errors.append(f"no_assertion_contract:{nodeid}")
    if asserts and all(_assert_is_constant_only(a) for a in asserts) and not has_raises_match:
        errors.append(f"constant_only_assertion:{nodeid}")
    if not has_required_call:
        errors.append(f"production_symbol_not_called:{bid}")
    if {"StoreVersion", "audit_market_store"}.issubset({c.split(".")[-1] for c in calls}) and not (set(row["production_symbols"]) == {"audit_market_store"}):
        errors.append(f"unrelated_noop_node:{nodeid}")
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
        expected_symbols = REQUIRED_PRODUCTION_SYMBOLS_064A35.get(bid)
        if (
            type(row["production_symbols"]) is not list
            or tuple(row["production_symbols"]) != expected_symbols
        ):
            errors.append(f"{path}:production_symbols_not_frozen:{bid}")
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
