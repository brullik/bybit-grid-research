#!/usr/bin/env python3
"""Validate changed paths against the PM active-task scope and PR mode."""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__:
    from .check_protected_paths import (
        _path_error,
        _SHA_RE,
        changed_paths_from_git,
        protected_path_errors,
    )
else:
    from check_protected_paths import (  # type: ignore[no-redef]
        _path_error,
        _SHA_RE,
        changed_paths_from_git,
        protected_path_errors,
    )

_KEYS = ("allowed_paths", "forbidden_paths", "required_paths", "schema", "task_id")
_SCHEMA = "pm_active_task_v1"
_OWNER = "brullik"
_TASK_FILE = "pm_acceptance/active_task.json"
_INACTIVE_TASK_ID = "NO_ACTIVE_IMPLEMENTATION"
_TASK_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_MODE_LABELS = frozenset({
    "pm-task-definition", "pm-control-plane", "pm-frozen-erratum", "pm-recovery-bundle"
})
_ERRATUM_SCHEMA = "pm_frozen_erratum_v1"
_ERRATUM_V2_SCHEMA = "pm_frozen_erratum_v2"
_ERRATUM_PREFIX = "pm_acceptance/errata/"
_ERRATUM_KEYS = frozenset({
    "base_sha256",
    "expected_red_failed_node_ids",
    "expected_red_passed_node_ids",
    "head_active_task_sha256",
    "head_sha256",
    "historical_active_task_commit_sha",
    "issue_number",
    "reason_code",
    "schema",
    "task_id",
    "test_path",
})
_ERRATUM_V2_KEYS = frozenset({
    *_ERRATUM_KEYS,
    "predecessor_commit_sha",
    "predecessor_manifest_sha256",
})
_RECOVERY_SCHEMA = "pm_recovery_bundle_v1"
_RECOVERY_BUNDLE_ID = "p0-recovery-walk-forward-committed-key"
_RECOVERY_MANIFEST_PATH = f"pm_acceptance/reactivations/{_RECOVERY_BUNDLE_ID}.json"
_RECOVERY_PREVIOUS_TASK_ID = "p0-walk-forward-exclusive-outcome-end"
_RECOVERY_SUSPENDED_TASK_ID = "p0-committed-key-preflight"
_RECOVERY_ALLOWED_PATHS = (
    "src/bybit_grid/research/scoring/outcome_grains.py",
    "src/bybit_grid/research/walk_forward/splits.py",
    "src/bybit_grid/research/walk_forward/leakage_audit.py",
    "scripts/check_scoring_review_pack.py", "scripts/make_scoring_review_pack.py",
    "tests/test_sprint_05_cost_scoring_walkforward.py",
    "tests/test_sprint_05_6_review_pack_closure.py",
    "tests/test_persisted_exclusive_outcome_end_walk_forward.py",
    "src/bybit_grid/data/market_store/models.py",
    "src/bybit_grid/data/market_store/import_public_batch.py",
    "src/bybit_grid/data/market_store/transaction.py",
    "tests/test_store_committed_key_preflight.py",
)
_RECOVERY_KEYS = frozenset({"allowed_paths", "bundle_id", "previous_task", "schema", "suspended_task"})
_RECOVERY_PREVIOUS_KEYS = frozenset({
    "contract_path", "corrected_frozen_test_sha256", "erratum_commit_sha",
    "erratum_manifest_path", "erratum_manifest_sha256", "expected_red_node_ids",
    "historical_activation_commit_sha", "historical_active_task_sha256",
    "historical_contract_sha256", "historical_frozen_test_sha256", "issue_number",
    "red_sentinel", "task_id", "test_path",
})
_RECOVERY_SUSPENDED_KEYS = frozenset({
    "contract_path", "expected_red_node_ids", "historical_activation_commit_sha",
    "historical_active_task_sha256", "historical_contract_sha256",
    "historical_frozen_test_sha256", "issue_number", "red_sentinel",
    "suspension_commit_sha", "task_id", "test_path",
})
_RECOVERY_PREVIOUS_FIXED: dict[str, str | int] = {
    "task_id": _RECOVERY_PREVIOUS_TASK_ID, "issue_number": 156,
    "historical_activation_commit_sha": "1305abb1517944e2cc9790e5546ca52ae66f592e",
    "historical_active_task_sha256": "85e9d288d637d15166da83557ae5462d43a021cc9f6ebc0a3f1b753f8e43597e",
    "historical_frozen_test_sha256": "1b77336ba734f0e6b464c9f8304add0c21c707703d800f699f8e68f5e1f4b09e",
    "historical_contract_sha256": "6f73875f71defa7c3d6ed824798d795339667391a9860741d3d67f3bf3ec0f05",
    "test_path": "pm_acceptance/tasks/p0-walk-forward-exclusive-outcome-end/test_walk_forward_exclusive_outcome_end.py",
    "contract_path": "docs/frozen_contracts/tasks/p0-walk-forward-exclusive-outcome-end.md",
    "erratum_manifest_path": "pm_acceptance/errata/p0-walk-forward-exclusive-outcome-end.json",
    "red_sentinel": "persisted_exclusive_outcome_end_walk_forward_contract_unavailable",
}
_RECOVERY_SUSPENDED_FIXED: dict[str, str | int] = {
    "task_id": _RECOVERY_SUSPENDED_TASK_ID, "issue_number": 157,
    "historical_activation_commit_sha": "3b826f2a6a3b02897047a30de8e920e2f5b72431",
    "historical_active_task_sha256": "248e518d84d7fa43ccc0536145e7d61e2e427df64b5d18825626da872cb15a89",
    "historical_frozen_test_sha256": "d7734ba1f0f3c42df0927c843c1691003de906ef3ad2cfd8e88ba3ac6512f513",
    "historical_contract_sha256": "21cc51b5e8f6ffece6af18f7a6c674309915ca6018dbe9f5011174f72d895696",
    "test_path": "pm_acceptance/tasks/p0-committed-key-preflight/test_store_committed_key_preflight.py",
    "contract_path": "docs/frozen_contracts/tasks/p0-committed-key-preflight.md",
    "red_sentinel": "committed_key_preflight_contract_unavailable",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_CONTROL_PLANE_ALLOWED = frozenset({
    "AGENTS.md",
    ".github/CODEOWNERS",
    ".github/workflows/pm-acceptance.yml",
    "scripts/check_protected_paths.py",
    "scripts/check_task_scope.py",
    "pm_acceptance/README.md",
    "pm_acceptance/test_control_plane_self.py",
    "docs/frozen_contracts/control_plane_v1.md",
})
_FORBIDDEN_ALWAYS = ("src/", "tests/")
_DEPENDENCY_EXACT = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
}
_DEPENDENCY_PREFIXES = ("requirements/",)
_FORBIDDEN_EXACT = set(_DEPENDENCY_EXACT)
_MANDATORY_FORBIDDEN_RULES = frozenset({
    "AGENTS.md",
    ".github/CODEOWNERS",
    ".github/workflows/**",
    ".github/actions/**",
    "pm_acceptance/**",
    "docs/frozen_contracts/**",
    "scripts/check_protected_paths.py",
    "scripts/check_task_scope.py",
    "scripts/check_numeric_environment.py",
    "scripts/check_no_live_execution.py",
    "conftest.py",
    "pytest.ini",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "noxfile.py",
    "sitecustomize.py",
    "usercustomize.py",
    "sitecustomize/**",
    "usercustomize/**",
    "src/sitecustomize.py",
    "src/usercustomize.py",
    "src/sitecustomize/**",
    "src/usercustomize/**",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements/*.txt",
    "uv.lock",
    "poetry.lock",
    "Pipfile",
    "Pipfile.lock",
})


@dataclass(frozen=True)
class ActiveTask:
    schema: str
    task_id: str
    allowed_paths: tuple[str, ...]
    required_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]


@dataclass(frozen=True)
class FrozenErratumManifest:
    schema: str
    task_id: str
    issue_number: int
    test_path: str
    base_sha256: str
    head_sha256: str
    head_active_task_sha256: str
    historical_active_task_commit_sha: str
    reason_code: str
    expected_red_failed_node_ids: tuple[str, ...]
    expected_red_passed_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class FrozenErratumV2Manifest:
    schema: str
    task_id: str
    issue_number: int
    test_path: str
    base_sha256: str
    head_sha256: str
    head_active_task_sha256: str
    historical_active_task_commit_sha: str
    predecessor_commit_sha: str
    predecessor_manifest_sha256: str
    reason_code: str
    expected_red_failed_node_ids: tuple[str, ...]
    expected_red_passed_node_ids: tuple[str, ...]


@dataclass(frozen=True)
class RecoveryBundleMember:
    task_id: str
    issue_number: int
    historical_activation_commit_sha: str
    historical_active_task_sha256: str
    historical_frozen_test_sha256: str
    historical_contract_sha256: str
    test_path: str
    contract_path: str
    red_sentinel: str
    expected_red_node_ids: tuple[str, ...]
    suspension_commit_sha: str | None = None
    erratum_commit_sha: str | None = None
    erratum_manifest_path: str | None = None
    erratum_manifest_sha256: str | None = None
    corrected_frozen_test_sha256: str | None = None


@dataclass(frozen=True)
class RecoveryBundleManifest:
    schema: str
    bundle_id: str
    allowed_paths: tuple[str, ...]
    previous_task: RecoveryBundleMember
    suspended_task: RecoveryBundleMember


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid_json_constant:{value}")


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate_json_key:{key}")
        out[key] = value
    return out


def _reject_float(value: str) -> None:
    raise ValueError(f"float_token:{value}")


def _validate_rule(rule: str) -> None:
    if rule == "requirements/*.txt":
        return
    if not isinstance(rule, str) or _path_error(rule[:-3] if rule.endswith("/**") else rule) is not None:
        raise ValueError(f"unsafe_rule:{rule}")
    body = rule[:-3] if rule.endswith("/**") else rule
    if not body or "*" in body or "?" in body or "[" in body or "]" in body:
        raise ValueError(f"invalid_rule:{rule}")


def _strings(name: str, value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"not_list:{name}")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"non_string:{name}")
        if item in seen:
            raise ValueError(f"duplicate_entry:{name}:{item}")
        _validate_rule(item)
        seen.add(item)
        out.append(item)
    return tuple(out)


def parse_labels_json(text: str) -> tuple[str, ...]:
    value = json.loads(
        text,
        object_pairs_hook=_pairs_hook,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, list):
        raise ValueError("labels_not_list")
    labels: list[str] = []
    seen: set[str] = set()
    for label in value:
        if not isinstance(label, str):
            raise ValueError("label_not_string")
        if label in seen:
            raise ValueError(f"duplicate_label:{label}")
        seen.add(label)
        labels.append(label)
    return tuple(labels)


def parse_active_task_bytes(data: bytes) -> ActiveTask:
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom")
    text = data.decode("utf-8", "strict")
    obj = json.loads(text, object_pairs_hook=_pairs_hook, parse_float=_reject_float, parse_constant=_reject_constant)
    if not isinstance(obj, dict):
        raise ValueError("task_not_object")
    if set(obj) != set(_KEYS):
        unknown = sorted(set(obj) - set(_KEYS))
        missing = sorted(set(_KEYS) - set(obj))
        raise ValueError(f"invalid_task_keys:missing={','.join(missing)}:unknown={','.join(unknown)}")
    if obj["schema"] != _SCHEMA or not isinstance(obj["schema"], str):
        raise ValueError("invalid_schema")
    if not isinstance(obj["task_id"], str) or not obj["task_id"]:
        raise ValueError("invalid_task_id")
    task = ActiveTask(
        schema=obj["schema"],
        task_id=obj["task_id"],
        allowed_paths=_strings("allowed_paths", obj["allowed_paths"]),
        required_paths=_strings("required_paths", obj["required_paths"]),
        forbidden_paths=_strings("forbidden_paths", obj["forbidden_paths"]),
    )
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if data != canonical:
        raise ValueError("noncanonical_task_bytes")
    return task


def _erratum_node_ids(name: str, value: Any, test_path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"not_list:{name}")
    out: list[str] = []
    seen: set[str] = set()
    prefix = f"{test_path}::"
    for node_id in value:
        if not isinstance(node_id, str):
            raise ValueError(f"non_string:{name}")
        if not node_id.startswith(prefix) or any(ord(ch) < 32 or ord(ch) == 127 for ch in node_id):
            raise ValueError(f"invalid_node_id:{name}:{node_id}")
        if node_id in seen:
            raise ValueError(f"duplicate_entry:{name}:{node_id}")
        seen.add(node_id)
        out.append(node_id)
    return tuple(out)


def parse_frozen_erratum_manifest_bytes(data: bytes) -> FrozenErratumManifest:
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom")
    text = data.decode("utf-8", "strict")
    obj = json.loads(
        text,
        object_pairs_hook=_pairs_hook,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )
    if not isinstance(obj, dict):
        raise ValueError("erratum_not_object")
    if set(obj) != _ERRATUM_KEYS:
        unknown = sorted(set(obj) - _ERRATUM_KEYS)
        missing = sorted(_ERRATUM_KEYS - set(obj))
        raise ValueError(
            f"invalid_erratum_keys:missing={','.join(missing)}:unknown={','.join(unknown)}"
        )
    if not isinstance(obj["schema"], str) or obj["schema"] != _ERRATUM_SCHEMA:
        raise ValueError("invalid_erratum_schema")
    task_id = obj["task_id"]
    if (
        not isinstance(task_id, str)
        or task_id == _INACTIVE_TASK_ID
        or not _TASK_ID_RE.fullmatch(task_id)
    ):
        raise ValueError("invalid_erratum_task_id")
    issue_number = obj["issue_number"]
    if type(issue_number) is not int or issue_number <= 0:
        raise ValueError("invalid_erratum_issue_number")
    test_path = obj["test_path"]
    if (
        not isinstance(test_path, str)
        or _path_error(test_path) is not None
        or not _erratum_test_path(task_id, test_path)
    ):
        raise ValueError("invalid_erratum_test_path")
    for key in ("base_sha256", "head_sha256", "head_active_task_sha256"):
        if not isinstance(obj[key], str) or not _SHA256_RE.fullmatch(obj[key]):
            raise ValueError(f"invalid_erratum_{key}")
    if obj["base_sha256"] == obj["head_sha256"]:
        raise ValueError("unchanged_erratum_test_sha256")
    historical_active_task_commit_sha = obj["historical_active_task_commit_sha"]
    if (
        not isinstance(historical_active_task_commit_sha, str)
        or not _COMMIT_SHA_RE.fullmatch(historical_active_task_commit_sha)
    ):
        raise ValueError("invalid_erratum_historical_active_task_commit_sha")
    reason_code = obj["reason_code"]
    if not isinstance(reason_code, str) or not _REASON_CODE_RE.fullmatch(reason_code):
        raise ValueError("invalid_erratum_reason_code")
    failed = _erratum_node_ids(
        "expected_red_failed_node_ids",
        obj["expected_red_failed_node_ids"],
        test_path,
    )
    passed = _erratum_node_ids(
        "expected_red_passed_node_ids",
        obj["expected_red_passed_node_ids"],
        test_path,
    )
    if not failed:
        raise ValueError("expected_red_failed_node_ids_empty")
    overlap = sorted(set(failed) & set(passed))
    if overlap:
        raise ValueError(f"red_node_id_outcome_overlap:{overlap[0]}")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if data != canonical:
        raise ValueError("noncanonical_erratum_bytes")
    return FrozenErratumManifest(
        schema=obj["schema"],
        task_id=task_id,
        issue_number=issue_number,
        test_path=test_path,
        base_sha256=obj["base_sha256"],
        head_sha256=obj["head_sha256"],
        head_active_task_sha256=obj["head_active_task_sha256"],
        historical_active_task_commit_sha=historical_active_task_commit_sha,
        reason_code=reason_code,
        expected_red_failed_node_ids=failed,
        expected_red_passed_node_ids=passed,
    )


def parse_frozen_erratum_v2_manifest_bytes(data: bytes) -> FrozenErratumV2Manifest:
    """Parse the single, audit-chained second erratum manifest."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("utf8_bom")
    text = data.decode("utf-8", "strict")
    obj = json.loads(
        text,
        object_pairs_hook=_pairs_hook,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )
    if not isinstance(obj, dict):
        raise ValueError("erratum_v2_not_object")
    if set(obj) != _ERRATUM_V2_KEYS:
        unknown = sorted(set(obj) - _ERRATUM_V2_KEYS)
        missing = sorted(_ERRATUM_V2_KEYS - set(obj))
        raise ValueError(
            f"invalid_erratum_v2_keys:missing={','.join(missing)}:unknown={','.join(unknown)}"
        )
    if not isinstance(obj["schema"], str) or obj["schema"] != _ERRATUM_V2_SCHEMA:
        raise ValueError("invalid_erratum_v2_schema")
    task_id = obj["task_id"]
    if (
        not isinstance(task_id, str)
        or task_id == _INACTIVE_TASK_ID
        or not _TASK_ID_RE.fullmatch(task_id)
    ):
        raise ValueError("invalid_erratum_v2_task_id")
    issue_number = obj["issue_number"]
    if type(issue_number) is not int or issue_number <= 0:
        raise ValueError("invalid_erratum_v2_issue_number")
    test_path = obj["test_path"]
    if (
        not isinstance(test_path, str)
        or _path_error(test_path) is not None
        or not _erratum_test_path(task_id, test_path)
    ):
        raise ValueError("invalid_erratum_v2_test_path")
    for key in (
        "base_sha256",
        "head_sha256",
        "head_active_task_sha256",
        "predecessor_manifest_sha256",
    ):
        if not isinstance(obj[key], str) or not _SHA256_RE.fullmatch(obj[key]):
            raise ValueError(f"invalid_erratum_v2_{key}")
    if obj["base_sha256"] == obj["head_sha256"]:
        raise ValueError("unchanged_erratum_v2_test_sha256")
    for key in ("historical_active_task_commit_sha", "predecessor_commit_sha"):
        if not isinstance(obj[key], str) or not _COMMIT_SHA_RE.fullmatch(obj[key]):
            raise ValueError(f"invalid_erratum_v2_{key}")
    reason_code = obj["reason_code"]
    if not isinstance(reason_code, str) or not _REASON_CODE_RE.fullmatch(reason_code):
        raise ValueError("invalid_erratum_v2_reason_code")
    failed = _erratum_node_ids(
        "expected_red_failed_node_ids",
        obj["expected_red_failed_node_ids"],
        test_path,
    )
    passed = _erratum_node_ids(
        "expected_red_passed_node_ids",
        obj["expected_red_passed_node_ids"],
        test_path,
    )
    if not failed:
        raise ValueError("expected_red_failed_node_ids_empty")
    overlap = sorted(set(failed) & set(passed))
    if overlap:
        raise ValueError(f"red_node_id_outcome_overlap:{overlap[0]}")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if data != canonical:
        raise ValueError("noncanonical_erratum_v2_bytes")
    return FrozenErratumV2Manifest(
        schema=obj["schema"],
        task_id=task_id,
        issue_number=issue_number,
        test_path=test_path,
        base_sha256=obj["base_sha256"],
        head_sha256=obj["head_sha256"],
        head_active_task_sha256=obj["head_active_task_sha256"],
        historical_active_task_commit_sha=obj["historical_active_task_commit_sha"],
        predecessor_commit_sha=obj["predecessor_commit_sha"],
        predecessor_manifest_sha256=obj["predecessor_manifest_sha256"],
        reason_code=reason_code,
        expected_red_failed_node_ids=failed,
        expected_red_passed_node_ids=passed,
    )


def _parse_recovery_member(
    value: Any,
    *,
    name: str,
    keys: frozenset[str],
    fixed: dict[str, str | int],
    expected_count: int,
) -> RecoveryBundleMember:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"invalid_recovery_{name}_keys")
    if type(value["issue_number"]) is not int or value["issue_number"] <= 0:
        raise ValueError(f"invalid_recovery_{name}_issue_number")
    for key, expected in fixed.items():
        if type(value[key]) is not type(expected) or value[key] != expected:
            raise ValueError(f"invalid_recovery_{name}_{key}")
    for key in (
        "historical_active_task_sha256", "historical_frozen_test_sha256",
        "historical_contract_sha256",
    ):
        if not isinstance(value[key], str) or _SHA256_RE.fullmatch(value[key]) is None:
            raise ValueError(f"invalid_recovery_{name}_{key}")
    if not isinstance(value["expected_red_node_ids"], list):
        raise ValueError(f"invalid_recovery_{name}_expected_red_node_ids")
    prefix = f'{value["test_path"]}::'
    node_ids: list[str] = []
    for node_id in value["expected_red_node_ids"]:
        if not isinstance(node_id, str) or not node_id.startswith(prefix):
            raise ValueError(f"invalid_recovery_{name}_expected_red_node_id")
        if node_id in node_ids:
            raise ValueError(f"duplicate_recovery_{name}_expected_red_node_id")
        node_ids.append(node_id)
    if len(node_ids) != expected_count:
        raise ValueError(f"invalid_recovery_{name}_expected_red_node_count:{len(node_ids)}")
    optional: dict[str, str | None] = {
        "suspension_commit_sha": None, "erratum_commit_sha": None,
        "erratum_manifest_path": None, "erratum_manifest_sha256": None,
        "corrected_frozen_test_sha256": None,
    }
    for key in tuple(optional):
        if key not in value:
            continue
        item = value[key]
        if key.endswith("_sha256"):
            valid = isinstance(item, str) and _SHA256_RE.fullmatch(item) is not None
        elif key.endswith("_commit_sha"):
            valid = isinstance(item, str) and _COMMIT_SHA_RE.fullmatch(item) is not None
        else:
            valid = isinstance(item, str) and _path_error(item) is None
        if not valid:
            raise ValueError(f"invalid_recovery_{name}_{key}")
        optional[key] = item
    return RecoveryBundleMember(
        task_id=value["task_id"], issue_number=value["issue_number"],
        historical_activation_commit_sha=value["historical_activation_commit_sha"],
        historical_active_task_sha256=value["historical_active_task_sha256"],
        historical_frozen_test_sha256=value["historical_frozen_test_sha256"],
        historical_contract_sha256=value["historical_contract_sha256"],
        test_path=value["test_path"], contract_path=value["contract_path"],
        red_sentinel=value["red_sentinel"], expected_red_node_ids=tuple(node_ids),
        **optional,
    )


def parse_recovery_bundle_manifest_bytes(data: bytes) -> RecoveryBundleManifest:
    """Parse the only supported two-task recovery permit."""
    obj = json.loads(
        data.decode("utf-8", "strict"), object_pairs_hook=_pairs_hook,
        parse_float=_reject_float, parse_constant=_reject_constant,
    )
    if not isinstance(obj, dict) or set(obj) != _RECOVERY_KEYS:
        raise ValueError("invalid_recovery_bundle_keys")
    if obj["schema"] != _RECOVERY_SCHEMA or not isinstance(obj["schema"], str):
        raise ValueError("invalid_recovery_bundle_schema")
    if obj["bundle_id"] != _RECOVERY_BUNDLE_ID or not isinstance(obj["bundle_id"], str):
        raise ValueError("invalid_recovery_bundle_id")
    if obj["allowed_paths"] != list(_RECOVERY_ALLOWED_PATHS):
        raise ValueError("invalid_recovery_allowed_paths")
    previous = _parse_recovery_member(
        obj["previous_task"], name="previous", keys=_RECOVERY_PREVIOUS_KEYS,
        fixed=_RECOVERY_PREVIOUS_FIXED, expected_count=32,
    )
    suspended = _parse_recovery_member(
        obj["suspended_task"], name="suspended", keys=_RECOVERY_SUSPENDED_KEYS,
        fixed=_RECOVERY_SUSPENDED_FIXED, expected_count=20,
    )
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if data != canonical:
        raise ValueError("noncanonical_recovery_bundle_bytes")
    return RecoveryBundleManifest(
        obj["schema"], obj["bundle_id"], tuple(obj["allowed_paths"]), previous, suspended
    )


def _matches(rule: str, path: str) -> bool:
    if rule == "requirements/*.txt":
        rest = path.removeprefix("requirements/")
        return path.startswith("requirements/") and "/" not in rest and rest.endswith(".txt")
    if rule.endswith("/**"):
        return path.startswith(rule[:-2])
    return path == rule


def _rule_covers(allowed_rule: str, required_rule: str) -> bool:
    if allowed_rule == "requirements/*.txt" or required_rule == "requirements/*.txt":
        return allowed_rule == required_rule
    if not allowed_rule.endswith("/**"):
        return allowed_rule == required_rule
    allowed_prefix = allowed_rule[:-2]
    if required_rule.endswith("/**"):
        required_root = required_rule[:-3]
        return f"{required_root}/".startswith(allowed_prefix)
    return required_rule.startswith(allowed_prefix)


def _rule_targets_protected_path(rule: str) -> bool:
    if rule == "requirements/*.txt":
        return True
    if rule.endswith("/**"):
        probe = f"{rule[:-3]}/__scope_probe__"
        return bool(protected_path_errors((probe,)))
    return bool(protected_path_errors((rule,)))


def _task_test_path(task_id: str, path: str) -> bool:
    prefix = f"pm_acceptance/tasks/{task_id}/"
    return path.startswith(prefix) and path.endswith(".py") and len(path) > len(prefix)


def _erratum_test_path(task_id: str, path: str) -> bool:
    expected_parent = f"pm_acceptance/tasks/{task_id}"
    parsed = Path(path)
    return (
        parsed.parent.as_posix() == expected_parent
        and parsed.name.startswith("test_")
        and parsed.suffix == ".py"
    )


def _task_contract_path(task_id: str) -> str:
    return f"docs/frozen_contracts/tasks/{task_id}.md"


def task_definition_transition_errors(
    base_task: ActiveTask,
    head_task: ActiveTask,
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    errors = _changed_path_errors(changed_paths)
    valid = [p for p in changed_paths if isinstance(p, str) and _path_error(p) is None]
    base_inactive = base_task.task_id == _INACTIVE_TASK_ID
    head_inactive = head_task.task_id == _INACTIVE_TASK_ID

    if base_inactive and not head_inactive:
        transition = "open"
    elif not base_inactive and head_inactive:
        transition = "close"
    else:
        errors.append(f"invalid_task_transition:{base_task.task_id}->{head_task.task_id}")
        return tuple(sorted(errors))

    if _TASK_FILE not in valid:
        errors.append("active_task_file_not_changed")

    missing_forbidden = sorted(_MANDATORY_FORBIDDEN_RULES - set(head_task.forbidden_paths))
    errors.extend(f"mandatory_forbidden_rule_missing:{rule}" for rule in missing_forbidden)

    if transition == "close":
        if head_task.allowed_paths:
            errors.append("close_task_allowed_paths_not_empty")
        if head_task.required_paths:
            errors.append("close_task_required_paths_not_empty")
        for path in valid:
            if path != _TASK_FILE:
                errors.append(f"close_task_extra_path:{path}")
        return tuple(sorted(errors))

    if not _TASK_ID_RE.fullmatch(head_task.task_id):
        errors.append(f"unsafe_task_id:{head_task.task_id}")
    if not head_task.allowed_paths:
        errors.append("open_task_allowed_paths_empty")
    if not head_task.required_paths:
        errors.append("open_task_required_paths_empty")
    for required_rule in head_task.required_paths:
        if not any(_rule_covers(allowed_rule, required_rule) for allowed_rule in head_task.allowed_paths):
            errors.append(f"required_rule_not_allowed:{required_rule}")
        if any(_rule_covers(forbidden_rule, required_rule) for forbidden_rule in head_task.forbidden_paths):
            errors.append(f"required_rule_forbidden:{required_rule}")
    for field_name, rules in (
        ("allowed", head_task.allowed_paths),
        ("required", head_task.required_paths),
    ):
        for rule in rules:
            if _rule_targets_protected_path(rule):
                errors.append(f"protected_{field_name}_rule:{rule}")

    task_test_found = False
    expected_contract = _task_contract_path(head_task.task_id)
    for path in valid:
        if path == _TASK_FILE:
            continue
        if path.startswith("pm_acceptance/tasks/"):
            if not _task_test_path(head_task.task_id, path):
                errors.append(f"task_id_path_mismatch:{path}")
                continue
            if Path(path).name == "conftest.py":
                errors.append(f"task_local_conftest_forbidden:{path}")
                continue
            if Path(path).name.startswith("test_"):
                task_test_found = True
            continue
        if path.startswith("docs/frozen_contracts/tasks/"):
            if path != expected_contract:
                errors.append(f"task_id_path_mismatch:{path}")
            continue
        errors.append(f"pm_task_definition_out_of_scope:{path}")
    if not task_test_found:
        errors.append(f"task_test_missing:{head_task.task_id}")
    return tuple(sorted(errors))


def _changed_path_errors(changed_paths: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    if type(changed_paths) is not tuple:
        return ["changed_paths_not_tuple"]
    seen: set[str] = set()
    for path in changed_paths:
        err = _path_error(path)
        if err:
            errors.append(err)
        elif path in seen:
            errors.append(f"duplicate_path:{path}")
        seen.add(path)
    return errors


def task_scope_errors(task: ActiveTask, changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    errors = _changed_path_errors(changed_paths)
    valid = [p for p in changed_paths if isinstance(p, str) and _path_error(p) is None]
    if task.task_id == _INACTIVE_TASK_ID:
        for path in valid:
            if path not in _CONTROL_PLANE_ALLOWED:
                errors.append(f"no_active_implementation_task:{path}")
    else:
        for path in valid:
            if not any(_matches(rule, path) for rule in task.allowed_paths):
                errors.append(f"out_of_scope_path:{path}")
    for path in valid:
        for rule in task.forbidden_paths:
            if _matches(rule, path):
                errors.append(f"forbidden_path_changed:{path}")
                break
    for rule in task.required_paths:
        if not any(_matches(rule, path) for path in valid):
            errors.append(f"required_path_missing:{rule}")
    return tuple(sorted(errors))


def classify_pr_mode(actor: str, labels: tuple[str, ...], changed_paths: tuple[str, ...]) -> tuple[str, tuple[str, ...]]:
    errors = _changed_path_errors(changed_paths)
    if type(labels) is not tuple:
        return "invalid", ("labels_not_tuple",)
    mode_labels = sorted(label for label in labels if label in _MODE_LABELS)
    unknown = sorted(label for label in labels if label.startswith("pm-") and label not in _MODE_LABELS)
    if unknown:
        errors.extend(f"unknown_mode_label:{label}" for label in unknown)
    if len(mode_labels) > 1:
        errors.append("multiple_mode_labels")
        return "invalid", tuple(sorted(errors))
    valid = [p for p in changed_paths if isinstance(p, str) and _path_error(p) is None]
    if len(mode_labels) == 1:
        label = mode_labels[0]
        if actor != _OWNER:
            errors.append(f"wrong_author:{actor}")
        if label == "pm-task-definition":
            mode = "pm-task-definition"
            for path in valid:
                task_path = path.startswith("pm_acceptance/tasks/")
                contract_path = path.startswith("docs/frozen_contracts/tasks/")
                if path != _TASK_FILE and not task_path and not contract_path:
                    errors.append(f"pm_task_definition_out_of_scope:{path}")
                if task_path and Path(path).name == "conftest.py":
                    errors.append(f"task_local_conftest_forbidden:{path}")
        elif label == "pm-frozen-erratum":
            mode = "pm-frozen-erratum"
            for path in valid:
                parts = Path(path).parts
                task_test = (
                    len(parts) == 4
                    and parts[:2] == ("pm_acceptance", "tasks")
                    and bool(_TASK_ID_RE.fullmatch(parts[2]))
                    and _erratum_test_path(parts[2], path)
                )
                erratum_manifest = path.startswith(_ERRATUM_PREFIX) and path.endswith(".json")
                if path != _TASK_FILE and not task_test and not erratum_manifest:
                    errors.append(f"pm_frozen_erratum_out_of_scope:{path}")
        elif label == "pm-recovery-bundle":
            mode = "pm-recovery-bundle"
            expected = {_TASK_FILE, _RECOVERY_MANIFEST_PATH}
            for path in valid:
                if path not in expected:
                    errors.append(f"pm_recovery_bundle_out_of_scope:{path}")
        else:
            mode = "pm-control-plane"
            for path in valid:
                if path not in _CONTROL_PLANE_ALLOWED:
                    errors.append(f"pm_control_plane_out_of_scope:{path}")
        for path in valid:
            if path.startswith(_FORBIDDEN_ALWAYS) or path in _FORBIDDEN_EXACT or path.startswith(_DEPENDENCY_PREFIXES):
                errors.append(f"production_path_forbidden_in_pm_mode:{path}")
        return mode, tuple(sorted(errors))
    for path in valid:
        if path in _CONTROL_PLANE_ALLOWED or path.startswith(("pm_acceptance/", "docs/frozen_contracts/", ".github/workflows/", ".github/actions/")):
            errors.append(f"missing_required_mode_label:{path}")
    return "implementation", tuple(sorted(errors))


def pr_mode_scope_errors(task: ActiveTask, changed_paths: tuple[str, ...], *, actor: str, labels: tuple[str, ...]) -> tuple[str, ...]:
    mode, mode_errors = classify_pr_mode(actor, labels, changed_paths)
    if mode_errors:
        return mode_errors
    if mode == "implementation":
        return tuple(sorted((*protected_path_errors(changed_paths), *task_scope_errors(task, changed_paths))))
    return ()


def acceptance_plan_for_mode(mode: str) -> tuple[str, ...]:
    if mode == "implementation":
        return ("base-isolated-acceptance",)
    if mode == "pm-control-plane":
        return ("base-control-plane-self-tests", "head-control-plane-self-tests")
    if mode == "pm-task-definition":
        return ("base-control-plane-self-tests", "head-task-definition-collect-only")
    if mode == "pm-frozen-erratum":
        return (
            "base-control-plane-self-tests",
            "head-frozen-erratum-exact-red",
        )
    if mode == "pm-recovery-bundle":
        return ("base-control-plane-self-tests", "head-recovery-bundle-exact-red")
    raise ValueError(f"invalid_mode:{mode}")


def git_blob_from_ref(ref: str, path: str) -> bytes:
    if not _SHA_RE.fullmatch(ref):
        raise ValueError("invalid_git_blob_ref")
    if _path_error(path) is not None:
        raise ValueError("invalid_git_blob_path")
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("head_active_task_unreadable")
    return proc.stdout


def git_object_exists(ref: str, path: str) -> bool:
    if not _SHA_RE.fullmatch(ref):
        raise ValueError("invalid_git_object_ref")
    if _path_error(path) is not None:
        raise ValueError("invalid_git_object_path")
    proc = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def git_is_ancestor(ancestor_sha: str, descendant_sha: str) -> bool:
    if not _COMMIT_SHA_RE.fullmatch(ancestor_sha):
        raise ValueError("invalid_git_ancestor_ref")
    if not _SHA_RE.fullmatch(descendant_sha):
        raise ValueError("invalid_git_descendant_ref")
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 1:
        return False
    raise RuntimeError("git_ancestor_check_failed")


def git_commit_parents(ref: str) -> tuple[str, ...]:
    proc = subprocess.run(
        ["git", "show", "-s", "--format=%P", ref], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("git_commit_parents_unreadable")
    return tuple(proc.stdout.strip().split())


def git_commit_parent_count(ref: str) -> int:
    return len(git_commit_parents(ref))


def git_first_parent_commit_count(path: str, blob_hash: str, ref: str) -> int:
    proc = subprocess.run(
        ["git", "rev-list", "--first-parent", ref, "--", path], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("git_first_parent_history_unreadable")
    count = 0
    for commit in proc.stdout.splitlines():
        try:
            data = git_blob_from_ref(commit, path)
        except RuntimeError:
            continue
        if hashlib.sha256(data).hexdigest() == blob_hash:
            count += 1
    return count


def _erratum_manifest_path(task_id: str) -> str:
    return f"{_ERRATUM_PREFIX}{task_id}.json"


def _erratum_v2_manifest_path(task_id: str) -> str:
    return f"{_ERRATUM_PREFIX}{task_id}.v2.json"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _qualified_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _contains_unsafe_exception(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, (ast.Tuple, ast.List)):
        return any(_contains_unsafe_exception(item) for item in node.elts)
    name = _qualified_name(node)
    return name in {"Exception", "BaseException", "builtins.Exception", "builtins.BaseException"}


class _FrozenTestInspector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.test_functions: list[tuple[str, str]] = []
        self.unsafe: list[str] = []
        self.immutable_test_depth = 0

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join((*self.scope, node.name))
        immutable_test = node.name.startswith("test_")
        if immutable_test:
            self.test_functions.append((qualified, ast.dump(node, include_attributes=False)))
            self.immutable_test_depth += 1
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()
        if immutable_test:
            self.immutable_test_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._visit_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        called = _qualified_name(node.func)
        mutable_harness = self.immutable_test_depth == 0
        if mutable_harness and called in {
            "pytest.skip",
            "pytest.xfail",
            "pytest.importorskip",
            "skip",
            "xfail",
            "importorskip",
        }:
            self.unsafe.append("skip_or_xfail")
        if mutable_harness and called in {"pytest.raises", "raises"}:
            expected = node.args[0] if node.args else next(
                (keyword.value for keyword in node.keywords if keyword.arg == "expected_exception"),
                None,
            )
            if _contains_unsafe_exception(expected):
                self.unsafe.append("broad_pytest_raises")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if self.immutable_test_depth == 0 and _contains_unsafe_exception(node.type):
            self.unsafe.append("broad_exception_handler")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if self.immutable_test_depth == 0 and node.attr.lower() in {
            "skip",
            "skipif",
            "skipunless",
            "xfail",
        }:
            name = _qualified_name(node)
            if name and (name.startswith("pytest.mark.") or name.startswith("unittest.")):
                self.unsafe.append("skip_or_xfail")
        self.generic_visit(node)


def _inspect_frozen_test(data: bytes) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    text = data.decode("utf-8", "strict")
    tree = ast.parse(text)
    inspector = _FrozenTestInspector()
    inspector.visit(tree)
    return tuple(inspector.test_functions), tuple(sorted(set(inspector.unsafe)))


def _active_erratum_task_errors(task: ActiveTask) -> list[str]:
    errors: list[str] = []
    if task.task_id == _INACTIVE_TASK_ID:
        return ["erratum_head_task_inactive"]
    if not _TASK_ID_RE.fullmatch(task.task_id):
        errors.append(f"unsafe_task_id:{task.task_id}")
    if not task.allowed_paths:
        errors.append("open_task_allowed_paths_empty")
    if not task.required_paths:
        errors.append("open_task_required_paths_empty")
    missing_forbidden = sorted(_MANDATORY_FORBIDDEN_RULES - set(task.forbidden_paths))
    errors.extend(f"mandatory_forbidden_rule_missing:{rule}" for rule in missing_forbidden)
    for required_rule in task.required_paths:
        if not any(_rule_covers(allowed_rule, required_rule) for allowed_rule in task.allowed_paths):
            errors.append(f"required_rule_not_allowed:{required_rule}")
        if any(_rule_covers(forbidden_rule, required_rule) for forbidden_rule in task.forbidden_paths):
            errors.append(f"required_rule_forbidden:{required_rule}")
    for field_name, rules in (("allowed", task.allowed_paths), ("required", task.required_paths)):
        for rule in rules:
            if _rule_targets_protected_path(rule):
                errors.append(f"protected_{field_name}_rule:{rule}")
    return errors


def frozen_erratum_transition_errors(
    base_sha: str,
    head_sha: str,
    base_task: ActiveTask,
    head_task: ActiveTask,
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    errors = _changed_path_errors(changed_paths)
    valid = [p for p in changed_paths if isinstance(p, str) and _path_error(p) is None]
    if base_task.task_id != _INACTIVE_TASK_ID:
        errors.append(f"erratum_base_task_not_inactive:{base_task.task_id}")
    errors.extend(_active_erratum_task_errors(head_task))
    if head_task.task_id == _INACTIVE_TASK_ID or not _TASK_ID_RE.fullmatch(head_task.task_id):
        return tuple(sorted(errors))

    manifest_path = _erratum_manifest_path(head_task.task_id)
    expected_fixed_paths = {_TASK_FILE, manifest_path}
    if len(valid) != 3:
        errors.append(f"frozen_erratum_changed_path_count:{len(valid)}")
    if _TASK_FILE not in valid:
        errors.append("active_task_file_not_changed")
    if manifest_path not in valid:
        errors.append(f"erratum_manifest_path_missing:{manifest_path}")
    for path in valid:
        task_test = _erratum_test_path(head_task.task_id, path)
        if path not in expected_fixed_paths and not task_test:
            errors.append(f"pm_frozen_erratum_out_of_scope:{path}")

    task_root = f"pm_acceptance/tasks/{head_task.task_id}"
    if not git_object_exists(base_sha, task_root):
        errors.append(f"erratum_base_task_missing:{head_task.task_id}")
    if not git_object_exists(base_sha, _task_contract_path(head_task.task_id)):
        errors.append(f"erratum_base_contract_missing:{head_task.task_id}")
    if git_object_exists(base_sha, manifest_path):
        errors.append(f"erratum_manifest_already_exists:{manifest_path}")
    if not git_object_exists(head_sha, manifest_path):
        errors.append(f"head_erratum_manifest_missing:{manifest_path}")
        return tuple(sorted(errors))

    try:
        manifest_bytes = git_blob_from_ref(head_sha, manifest_path)
        manifest = parse_frozen_erratum_manifest_bytes(manifest_bytes)
    except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
        errors.append(str(exc))
        return tuple(sorted(errors))
    if manifest.task_id != head_task.task_id:
        errors.append(f"erratum_task_id_mismatch:{manifest.task_id}")
    if manifest.head_active_task_sha256 != _sha256(_task_bytes_for_hash(head_task)):
        errors.append("head_active_task_sha256_mismatch")
    try:
        historical_is_ancestor = git_is_ancestor(
            manifest.historical_active_task_commit_sha,
            base_sha,
        )
    except (RuntimeError, ValueError) as exc:
        errors.append(str(exc))
        historical_is_ancestor = False
    if not historical_is_ancestor:
        errors.append("historical_active_task_commit_not_ancestor")
    else:
        try:
            historical_task_bytes = git_blob_from_ref(
                manifest.historical_active_task_commit_sha,
                _TASK_FILE,
            )
            head_task_bytes = git_blob_from_ref(head_sha, _TASK_FILE)
            parse_active_task_bytes(historical_task_bytes)
        except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"historical_active_task_unreadable:{type(exc).__name__}")
        else:
            if historical_task_bytes != head_task_bytes:
                errors.append("historical_active_task_bytes_mismatch")

    test_paths = [path for path in valid if _erratum_test_path(head_task.task_id, path)]
    if test_paths != [manifest.test_path]:
        errors.append("erratum_test_path_scope_mismatch")
    if not git_object_exists(base_sha, manifest.test_path):
        errors.append(f"base_erratum_test_missing:{manifest.test_path}")
        return tuple(sorted(errors))
    if not git_object_exists(head_sha, manifest.test_path):
        errors.append(f"head_erratum_test_missing:{manifest.test_path}")
        return tuple(sorted(errors))

    try:
        base_test = git_blob_from_ref(base_sha, manifest.test_path)
        head_test = git_blob_from_ref(head_sha, manifest.test_path)
        base_functions, _ = _inspect_frozen_test(base_test)
        head_functions, unsafe = _inspect_frozen_test(head_test)
    except (RuntimeError, SyntaxError, UnicodeDecodeError) as exc:
        errors.append(f"erratum_test_unreadable:{type(exc).__name__}")
        return tuple(sorted(errors))
    if _sha256(base_test) != manifest.base_sha256:
        errors.append("base_erratum_test_sha256_mismatch")
    if _sha256(head_test) != manifest.head_sha256:
        errors.append("head_erratum_test_sha256_mismatch")
    if base_functions != head_functions:
        errors.append("frozen_test_function_ast_changed")
    if not head_functions:
        errors.append("frozen_test_functions_missing")
    errors.extend(f"unsafe_frozen_test_pattern:{kind}" for kind in unsafe)

    expected_node_ids = (
        *manifest.expected_red_failed_node_ids,
        *manifest.expected_red_passed_node_ids,
    )
    declared_test_names = {
        node_id.rsplit("::", 1)[-1].split("[", 1)[0]
        for node_id in expected_node_ids
    }
    actual_test_names = {qualified.rsplit(".", 1)[-1] for qualified, _dump in head_functions}
    unknown_names = sorted(declared_test_names - actual_test_names)
    missing_names = sorted(actual_test_names - declared_test_names)
    errors.extend(f"unknown_erratum_red_test:{name}" for name in unknown_names)
    errors.extend(f"missing_erratum_red_test:{name}" for name in missing_names)
    return tuple(sorted(errors))


def frozen_erratum_v2_transition_errors(
    base_sha: str,
    head_sha: str,
    base_task: ActiveTask,
    head_task: ActiveTask,
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate the one-and-only second repair, chained to the immutable v1 repair."""
    errors = _changed_path_errors(changed_paths)
    valid = [p for p in changed_paths if isinstance(p, str) and _path_error(p) is None]
    if base_task.task_id != _INACTIVE_TASK_ID:
        errors.append(f"erratum_v2_base_task_not_inactive:{base_task.task_id}")
    errors.extend(_active_erratum_task_errors(head_task))
    if head_task.task_id == _INACTIVE_TASK_ID or not _TASK_ID_RE.fullmatch(head_task.task_id):
        return tuple(sorted(errors))

    predecessor_path = _erratum_manifest_path(head_task.task_id)
    manifest_path = _erratum_v2_manifest_path(head_task.task_id)
    expected_fixed_paths = {_TASK_FILE, manifest_path}
    if len(valid) != 3:
        errors.append(f"frozen_erratum_v2_changed_path_count:{len(valid)}")
    if _TASK_FILE not in valid:
        errors.append("active_task_file_not_changed")
    if manifest_path not in valid:
        errors.append(f"erratum_v2_manifest_path_missing:{manifest_path}")
    for path in valid:
        task_test = _erratum_test_path(head_task.task_id, path)
        if path not in expected_fixed_paths and not task_test:
            errors.append(f"pm_frozen_erratum_v2_out_of_scope:{path}")

    task_root = f"pm_acceptance/tasks/{head_task.task_id}"
    if not git_object_exists(base_sha, task_root):
        errors.append(f"erratum_v2_base_task_missing:{head_task.task_id}")
    if not git_object_exists(base_sha, _task_contract_path(head_task.task_id)):
        errors.append(f"erratum_v2_base_contract_missing:{head_task.task_id}")
    if not git_object_exists(base_sha, predecessor_path):
        errors.append(f"erratum_v2_predecessor_manifest_missing:{predecessor_path}")
        return tuple(sorted(errors))
    if git_object_exists(base_sha, manifest_path):
        errors.append(f"erratum_v2_manifest_already_exists:{manifest_path}")
    if not git_object_exists(head_sha, manifest_path):
        errors.append(f"head_erratum_v2_manifest_missing:{manifest_path}")
        return tuple(sorted(errors))

    try:
        predecessor_bytes = git_blob_from_ref(base_sha, predecessor_path)
        predecessor = parse_frozen_erratum_manifest_bytes(predecessor_bytes)
    except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
        errors.append(f"erratum_v2_predecessor_manifest_unreadable:{type(exc).__name__}")
        return tuple(sorted(errors))
    try:
        manifest_bytes = git_blob_from_ref(head_sha, manifest_path)
        manifest = parse_frozen_erratum_v2_manifest_bytes(manifest_bytes)
    except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
        errors.append(str(exc))
        return tuple(sorted(errors))

    if manifest.task_id != head_task.task_id:
        errors.append(f"erratum_v2_task_id_mismatch:{manifest.task_id}")
    if predecessor.task_id != head_task.task_id:
        errors.append(f"erratum_v2_predecessor_task_id_mismatch:{predecessor.task_id}")
    if predecessor.test_path != manifest.test_path:
        errors.append("erratum_v2_predecessor_test_path_mismatch")
    if predecessor.issue_number != manifest.issue_number:
        errors.append("erratum_v2_predecessor_issue_number_mismatch")
    if manifest.predecessor_manifest_sha256 != _sha256(predecessor_bytes):
        errors.append("erratum_v2_predecessor_manifest_sha256_mismatch")
    if predecessor.head_sha256 != manifest.base_sha256:
        errors.append("erratum_v2_predecessor_test_sha256_mismatch")
    if predecessor.head_active_task_sha256 != manifest.head_active_task_sha256:
        errors.append("erratum_v2_predecessor_active_task_sha256_mismatch")
    if (
        predecessor.historical_active_task_commit_sha
        != manifest.historical_active_task_commit_sha
    ):
        errors.append("erratum_v2_historical_active_task_commit_mismatch")
    if manifest.head_active_task_sha256 != _sha256(_task_bytes_for_hash(head_task)):
        errors.append("head_active_task_sha256_mismatch")

    try:
        predecessor_is_ancestor = git_is_ancestor(manifest.predecessor_commit_sha, base_sha)
    except (RuntimeError, ValueError) as exc:
        errors.append(str(exc))
        predecessor_is_ancestor = False
    if not predecessor_is_ancestor:
        errors.append("erratum_v2_predecessor_commit_not_ancestor")
    else:
        try:
            commit_manifest_bytes = git_blob_from_ref(
                manifest.predecessor_commit_sha,
                predecessor_path,
            )
            commit_test_bytes = git_blob_from_ref(
                manifest.predecessor_commit_sha,
                manifest.test_path,
            )
            commit_task_bytes = git_blob_from_ref(
                manifest.predecessor_commit_sha,
                _TASK_FILE,
            )
            parse_active_task_bytes(commit_task_bytes)
        except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"erratum_v2_predecessor_commit_unreadable:{type(exc).__name__}")
        else:
            if commit_manifest_bytes != predecessor_bytes:
                errors.append("erratum_v2_predecessor_manifest_bytes_mismatch")
            if _sha256(commit_test_bytes) != manifest.base_sha256:
                errors.append("erratum_v2_predecessor_commit_test_sha256_mismatch")
            try:
                head_task_bytes = git_blob_from_ref(head_sha, _TASK_FILE)
            except RuntimeError:
                errors.append("head_active_task_unreadable")
            else:
                if commit_task_bytes != head_task_bytes:
                    errors.append("erratum_v2_predecessor_active_task_bytes_mismatch")

    try:
        historical_is_ancestor = git_is_ancestor(
            manifest.historical_active_task_commit_sha,
            manifest.predecessor_commit_sha,
        )
    except (RuntimeError, ValueError) as exc:
        errors.append(str(exc))
        historical_is_ancestor = False
    if not historical_is_ancestor:
        errors.append("historical_active_task_commit_not_predecessor_ancestor")
    else:
        try:
            historical_task_bytes = git_blob_from_ref(
                manifest.historical_active_task_commit_sha,
                _TASK_FILE,
            )
            head_task_bytes = git_blob_from_ref(head_sha, _TASK_FILE)
            parse_active_task_bytes(historical_task_bytes)
        except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"historical_active_task_unreadable:{type(exc).__name__}")
        else:
            if historical_task_bytes != head_task_bytes:
                errors.append("historical_active_task_bytes_mismatch")

    test_paths = [path for path in valid if _erratum_test_path(head_task.task_id, path)]
    if test_paths != [manifest.test_path]:
        errors.append("erratum_v2_test_path_scope_mismatch")
    if not git_object_exists(base_sha, manifest.test_path):
        errors.append(f"base_erratum_v2_test_missing:{manifest.test_path}")
        return tuple(sorted(errors))
    if not git_object_exists(head_sha, manifest.test_path):
        errors.append(f"head_erratum_v2_test_missing:{manifest.test_path}")
        return tuple(sorted(errors))

    try:
        base_test = git_blob_from_ref(base_sha, manifest.test_path)
        head_test = git_blob_from_ref(head_sha, manifest.test_path)
        base_functions, _ = _inspect_frozen_test(base_test)
        head_functions, unsafe = _inspect_frozen_test(head_test)
    except (RuntimeError, SyntaxError, UnicodeDecodeError) as exc:
        errors.append(f"erratum_v2_test_unreadable:{type(exc).__name__}")
        return tuple(sorted(errors))
    if _sha256(base_test) != manifest.base_sha256:
        errors.append("base_erratum_v2_test_sha256_mismatch")
    if _sha256(head_test) != manifest.head_sha256:
        errors.append("head_erratum_v2_test_sha256_mismatch")
    if base_functions != head_functions:
        errors.append("frozen_test_function_ast_changed")
    if not head_functions:
        errors.append("frozen_test_functions_missing")
    errors.extend(f"unsafe_frozen_test_pattern:{kind}" for kind in unsafe)

    expected_node_ids = (
        *manifest.expected_red_failed_node_ids,
        *manifest.expected_red_passed_node_ids,
    )
    declared_test_names = {
        node_id.rsplit("::", 1)[-1].split("[", 1)[0]
        for node_id in expected_node_ids
    }
    actual_test_names = {qualified.rsplit(".", 1)[-1] for qualified, _dump in head_functions}
    unknown_names = sorted(declared_test_names - actual_test_names)
    missing_names = sorted(actual_test_names - declared_test_names)
    errors.extend(f"unknown_erratum_red_test:{name}" for name in unknown_names)
    errors.extend(f"missing_erratum_red_test:{name}" for name in missing_names)
    return tuple(sorted(errors))


def recovery_bundle_transition_errors(
    base_sha: str,
    head_sha: str,
    base_task: ActiveTask,
    head_task: ActiveTask,
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate the named, one-time, direct two-task recovery transition."""
    errors = _changed_path_errors(changed_paths)
    valid = [path for path in changed_paths if isinstance(path, str) and _path_error(path) is None]
    if base_task.task_id != _RECOVERY_PREVIOUS_TASK_ID:
        errors.append("recovery_base_task_mismatch")
    if head_task.task_id != _RECOVERY_BUNDLE_ID:
        errors.append("recovery_head_task_mismatch")
    if len(valid) != 2:
        errors.append(f"recovery_bundle_changed_path_count:{len(valid)}")
    expected_paths = {_TASK_FILE, _RECOVERY_MANIFEST_PATH}
    errors.extend(
        f"pm_recovery_bundle_out_of_scope:{path}" for path in valid if path not in expected_paths
    )
    errors.extend(
        f"recovery_bundle_path_missing:{path}" for path in sorted(expected_paths - set(valid))
    )
    if tuple(head_task.allowed_paths) != _RECOVERY_ALLOWED_PATHS:
        errors.append("recovery_allowed_paths_mismatch")
    if tuple(head_task.required_paths) != _RECOVERY_ALLOWED_PATHS:
        errors.append("recovery_required_paths_mismatch")
    if git_object_exists(base_sha, _RECOVERY_MANIFEST_PATH):
        errors.append("recovery_bundle_already_used")
    if not git_object_exists(head_sha, _RECOVERY_MANIFEST_PATH):
        errors.append("head_recovery_manifest_missing")
        return tuple(sorted(errors))
    try:
        manifest = parse_recovery_bundle_manifest_bytes(
            git_blob_from_ref(head_sha, _RECOVERY_MANIFEST_PATH)
        )
    except (RuntimeError, UnicodeDecodeError, ValueError) as exc:
        errors.append(str(exc))
        return tuple(sorted(errors))
    if manifest.allowed_paths != tuple(head_task.allowed_paths):
        errors.append("recovery_manifest_task_scope_mismatch")
    try:
        if git_commit_parent_count(head_sha) != 1:
            errors.append("recovery_head_not_single_parent")
        elif git_commit_parents(head_sha) != (base_sha,):
            errors.append("recovery_head_not_directly_based")
    except RuntimeError as exc:
        errors.append(str(exc))
    previous = manifest.previous_task
    suspended = manifest.suspended_task
    checks = (
        (previous.test_path, previous.historical_frozen_test_sha256, previous.historical_activation_commit_sha, "previous_historical_test"),
        (previous.contract_path, previous.historical_contract_sha256, previous.historical_activation_commit_sha, "previous_historical_contract"),
        (_TASK_FILE, previous.historical_active_task_sha256, previous.historical_activation_commit_sha, "previous_historical_task"),
        (suspended.test_path, suspended.historical_frozen_test_sha256, suspended.historical_activation_commit_sha, "suspended_historical_test"),
        (suspended.contract_path, suspended.historical_contract_sha256, suspended.historical_activation_commit_sha, "suspended_historical_contract"),
        (_TASK_FILE, suspended.historical_active_task_sha256, suspended.historical_activation_commit_sha, "suspended_historical_task"),
        (previous.erratum_manifest_path or "", previous.erratum_manifest_sha256 or "", previous.erratum_commit_sha or "", "previous_erratum_manifest"),
        (previous.test_path, previous.corrected_frozen_test_sha256 or "", previous.erratum_commit_sha or "", "previous_corrected_test"),
    )
    for path, digest, ref, label in checks:
        try:
            count = git_first_parent_commit_count(path, digest, ref)
        except RuntimeError:
            errors.append(f"recovery_{label}_unreadable")
        else:
            if count != 1:
                errors.append(f"recovery_{label}_count:{count}")
    for ancestor, descendant, label in (
        (previous.historical_activation_commit_sha, previous.erratum_commit_sha or "", "previous_activation"),
        (suspended.historical_activation_commit_sha, suspended.suspension_commit_sha or "", "suspended_activation"),
        (previous.erratum_commit_sha or "", base_sha, "erratum_base"),
        (suspended.suspension_commit_sha or "", base_sha, "suspension_base"),
    ):
        if not git_is_ancestor(ancestor, descendant):
            errors.append(f"recovery_{label}_not_ancestor")
    try:
        if git_blob_from_ref(previous.erratum_commit_sha or "", _TASK_FILE) != _task_bytes_for_hash(base_task):
            errors.append("recovery_erratum_task_bytes_mismatch")
        inactive = ActiveTask(_SCHEMA, _INACTIVE_TASK_ID, (), (), head_task.forbidden_paths)
        if git_blob_from_ref(suspended.suspension_commit_sha or "", _TASK_FILE) != _task_bytes_for_hash(inactive):
            errors.append("recovery_suspension_not_canonical_inactive")
    except RuntimeError as exc:
        errors.append(str(exc))
    return tuple(sorted(errors))


def _task_bytes_for_hash(task: ActiveTask) -> bytes:
    obj = {
        "allowed_paths": list(task.allowed_paths),
        "forbidden_paths": list(task.forbidden_paths),
        "required_paths": list(task.required_paths),
        "schema": task.schema,
        "task_id": task.task_id,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def task_definition_head_path_errors(
    head_sha: str,
    head_task: ActiveTask,
    changed_paths: tuple[str, ...],
) -> tuple[str, ...]:
    if head_task.task_id == _INACTIVE_TASK_ID:
        return ()
    errors: list[str] = []
    expected_contract = _task_contract_path(head_task.task_id)
    for path in changed_paths:
        if not (_task_test_path(head_task.task_id, path) or path == expected_contract):
            continue
        try:
            data = git_blob_from_ref(head_sha, path)
        except RuntimeError:
            errors.append(f"head_task_path_missing:{path}")
            continue
        try:
            data.decode("utf-8", "strict")
        except UnicodeDecodeError:
            errors.append(f"head_task_path_not_utf8:{path}")
    return tuple(sorted(errors))


def task_definition_base_path_errors(
    base_sha: str,
    base_task: ActiveTask,
    head_task: ActiveTask,
) -> tuple[str, ...]:
    if base_task.task_id != _INACTIVE_TASK_ID or head_task.task_id == _INACTIVE_TASK_ID:
        return ()
    if not _TASK_ID_RE.fullmatch(head_task.task_id):
        return ()
    errors: list[str] = []
    task_root = f"pm_acceptance/tasks/{head_task.task_id}"
    if git_object_exists(base_sha, task_root):
        errors.append(f"task_id_reused:{head_task.task_id}")
    if git_object_exists(base_sha, _task_contract_path(head_task.task_id)):
        errors.append(f"task_contract_id_reused:{head_task.task_id}")
    return tuple(errors)


def run_exact_control_plane_self_tests(root: Path) -> int:
    """Require one plain passing call for every collected control-plane self-test."""
    try:
        root = root.resolve(strict=True)
    except OSError as exc:
        print(json.dumps({"errors": [f"control_plane_root_unreadable:{type(exc).__name__}"], "ok": False}))
        return 1
    test_path = root / "pm_acceptance/test_control_plane_self.py"
    config_path = root / "pytest.ini"
    if not root.is_dir() or not test_path.is_file() or not config_path.is_file():
        print(json.dumps({"errors": ["control_plane_self_test_harness_incomplete"], "ok": False}))
        return 1
    result_path = root.parent / f".control-plane-self-{os.getpid()}.json"
    result_path.unlink(missing_ok=True)
    child = r'''
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


class ExactPlainPasses:
    def __init__(self) -> None:
        self.call_node_ids: set[str] = set()
        self.collected: list[str] = []
        self.forbidden: list[str] = []
        self.passed: list[str] = []

    def pytest_collection_finish(self, session) -> None:
        self.collected = [item.nodeid for item in session.items]
        if len(set(self.collected)) != len(self.collected):
            self.forbidden.append("duplicate-collected-node-id")

    def pytest_collectreport(self, report) -> None:
        if report.outcome != "passed":
            self.forbidden.append(f"collect-{report.outcome}:{report.nodeid}")

    def pytest_deselected(self, items) -> None:
        self.forbidden.extend(f"deselected:{item.nodeid}" for item in items)

    def pytest_runtest_logreport(self, report) -> None:
        if getattr(report, "wasxfail", None) is not None:
            self.forbidden.append(f"xfail-or-xpass:{report.nodeid}:{report.when}")
        if report.when != "call":
            if report.outcome != "passed":
                self.forbidden.append(
                    f"non-call-{report.when}-{report.outcome}:{report.nodeid}"
                )
            return
        if report.nodeid in self.call_node_ids:
            self.forbidden.append(f"duplicate-call:{report.nodeid}")
            return
        self.call_node_ids.add(report.nodeid)
        if report.outcome == "passed":
            self.passed.append(report.nodeid)
        else:
            self.forbidden.append(f"call-{report.outcome}:{report.nodeid}")


root = Path(os.environ["EXACT_CONTROL_ROOT"])
outcomes = ExactPlainPasses()
exit_code = pytest.main(
    [
        str(root / "pm_acceptance/test_control_plane_self.py"),
        "-q",
        "-c",
        str(root / "pytest.ini"),
        f"--confcutdir={root / 'pm_acceptance'}",
    ],
    plugins=[outcomes],
)
Path(os.environ["EXACT_CONTROL_RESULT"]).write_text(
    json.dumps(
        {
            "call_node_ids": sorted(outcomes.call_node_ids),
            "collected": outcomes.collected,
            "exit_code": int(exit_code),
            "forbidden": outcomes.forbidden,
            "passed": outcomes.passed,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    + "\n",
    encoding="utf-8",
)
'''
    environment = dict(os.environ)
    environment.update({
        "EXACT_CONTROL_RESULT": str(result_path),
        "EXACT_CONTROL_ROOT": str(root),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    })
    result = subprocess.run(
        [sys.executable, "-c", child],
        cwd=root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result_path.is_file():
        result_path.unlink(missing_ok=True)
        payload = {
            "collected_count": 0,
            "errors": [f"control-plane-self-runner-failed:{result.returncode}"],
            "ok": False,
            "passed_count": 0,
        }
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return 1
    try:
        outcomes = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    finally:
        result_path.unlink(missing_ok=True)
    expected_keys = {"call_node_ids", "collected", "exit_code", "forbidden", "passed"}
    if not isinstance(outcomes, dict) or set(outcomes) != expected_keys:
        print(json.dumps({"errors": ["invalid_control_plane_self_result"], "ok": False}))
        return 1
    for key in ("call_node_ids", "collected", "forbidden", "passed"):
        value = outcomes[key]
        if (
            not isinstance(value, list)
            or any(not isinstance(item, str) or not item for item in value)
            or len(set(value)) != len(value)
        ):
            print(json.dumps({"errors": [f"invalid_control_plane_self_{key}"], "ok": False}))
            return 1

    collected = set(outcomes["collected"])
    call_node_ids = set(outcomes["call_node_ids"])
    forbidden = list(outcomes["forbidden"])
    passed = list(outcomes["passed"])
    forbidden.extend(f"missing-call:{node_id}" for node_id in sorted(collected - call_node_ids))
    forbidden.extend(f"call-not-collected:{node_id}" for node_id in sorted(call_node_ids - collected))
    errors: list[str] = []
    if type(outcomes["exit_code"]) is not int or outcomes["exit_code"] != 0:
        errors.append(f"unexpected-pytest-exit:{outcomes['exit_code']}")
    if not outcomes["collected"]:
        errors.append("empty-collection")
    errors.extend(forbidden)
    if set(passed) != collected or len(passed) != len(outcomes["collected"]):
        errors.append("plain-pass-set-mismatch")
    payload = {
        "collected_count": len(outcomes["collected"]),
        "errors": sorted(set(errors)),
        "ok": not errors,
        "passed_count": len(passed),
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if not errors else 1


def _emit(
    changed_count: int,
    errors: tuple[str, ...],
    mode: str | None = None,
    task_id: str | None = None,
) -> int:
    payload: dict[str, object] = {"changed_count": changed_count, "errors": list(errors), "ok": not errors}
    if mode is not None:
        payload["mode"] = mode
    if task_id is not None:
        payload["task_id"] = task_id
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if "--exact-control-plane-root" in effective_argv:
        exact_parser = argparse.ArgumentParser(add_help=True)
        exact_parser.add_argument("--exact-control-plane-root", required=True)
        exact_args = exact_parser.parse_args(effective_argv)
        return run_exact_control_plane_self_tests(Path(exact_args.exact_control_plane_root))
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--task-file", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--actor", default="")
    parser.add_argument("--labels-json", default="[]")
    args = parser.parse_args(effective_argv)
    errors: list[str] = []
    if args.task_file != _TASK_FILE:
        errors.append("invalid_task_file")
    if not _SHA_RE.fullmatch(args.base_sha):
        errors.append("invalid_base_sha")
    if not _SHA_RE.fullmatch(args.head_sha):
        errors.append("invalid_head_sha")
    if errors:
        return _emit(0, tuple(sorted(errors)))
    try:
        task = parse_active_task_bytes(Path(args.task_file).read_bytes())
        changed = changed_paths_from_git(args.base_sha, args.head_sha)
        labels = parse_labels_json(args.labels_json)
        mode, mode_errors = classify_pr_mode(args.actor, labels, changed)
        if mode_errors:
            return _emit(len(changed), mode_errors, mode, task.task_id)
        if mode == "implementation":
            errors_tuple = tuple(sorted((*protected_path_errors(changed), *task_scope_errors(task, changed))))
            return _emit(len(changed), errors_tuple, mode, task.task_id)
        if mode == "pm-task-definition":
            head_task = parse_active_task_bytes(git_blob_from_ref(args.head_sha, _TASK_FILE))
            transition_errors = tuple(sorted((
                *task_definition_transition_errors(task, head_task, changed),
                *task_definition_base_path_errors(args.base_sha, task, head_task),
                *task_definition_head_path_errors(args.head_sha, head_task, changed),
            )))
            return _emit(len(changed), transition_errors, mode, head_task.task_id)
        if mode == "pm-frozen-erratum":
            head_task = parse_active_task_bytes(git_blob_from_ref(args.head_sha, _TASK_FILE))
            v2_manifest_path = _erratum_v2_manifest_path(head_task.task_id)
            if v2_manifest_path in changed:
                erratum_errors = frozen_erratum_v2_transition_errors(
                    args.base_sha,
                    args.head_sha,
                    task,
                    head_task,
                    changed,
                )
            else:
                erratum_errors = frozen_erratum_transition_errors(
                    args.base_sha,
                    args.head_sha,
                    task,
                    head_task,
                    changed,
                )
            return _emit(len(changed), erratum_errors, mode, head_task.task_id)
        if mode == "pm-recovery-bundle":
            head_task = parse_active_task_bytes(git_blob_from_ref(args.head_sha, _TASK_FILE))
            transition_errors = recovery_bundle_transition_errors(
                args.base_sha, args.head_sha, task, head_task, changed
            )
            return _emit(len(changed), transition_errors, mode, head_task.task_id)
        return _emit(len(changed), (), mode, task.task_id)
    except (OSError, RuntimeError, UnicodeDecodeError, ValueError) as exc:
        return _emit(0, (str(exc),))


if __name__ == "__main__":
    sys.exit(main())
