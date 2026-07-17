from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

import bybit_grid


TASK_ID = "pre-control-plane-assurance-matrix"
MATRIX_PATH = "docs/PRE_CONTROL_PLANE_ASSURANCE_MATRIX.md"
MARKER = "<!-- assurance-contract: pre-control-plane-v1 -->"
SENTINEL = "pre_control_plane_assurance_matrix_unavailable"
AUDIT_REF = "f7cab3fb2e08e3578cce1eb3830e944dbf0ecd0f"
COMMENT_ID = "4999418554"
MANIFEST_SHA256 = "c75783455ad5a5f21bbd718805691689f461f432cd0e9f853c454e7e9fc22e0e"
COMPONENT_ROWS_SHA256 = (
    "2fa79231654d6f49859fad39eb1fc264b06f0a79bfa76a3050f931e618a35715"
)
HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
JSON_FENCE = re.compile(r"```json\s*\n([\s\S]*?)\n```")
PAIR = re.compile(r"`([a-z][a-z0-9_]*)`:\s*`([^`]+)`")
COMPONENT_ROW = re.compile(
    r"^\| (C\d{2}) \| ([^|]+) \| ([^|]+) \| `([A-Z_]+)` \| ([^|]+) \|$",
    re.MULTILINE,
)
ROOT = Path(bybit_grid.__file__).resolve().parents[2]

EXPECTED_TOP_LEVEL = {
    "accepted_governed_chains",
    "audit_ref",
    "disposition_summary",
    "method",
    "prs",
    "quarantined_chains",
    "removed_paths",
    "residual_issues",
    "surviving_current_path_count",
    "unique_historical_path_count",
}
EXPECTED_METHOD = {
    "historical_code_executed": False,
    "historical_code_imported": False,
    "credentials_used": False,
    "private_api_called": False,
    "bybit_public_capture_used": False,
    "live_execution_used": False,
    "trading_mutation_used": False,
    "current_green_is_retroactive_proof": False,
}
EXPECTED_REMOVED = [
    "numpy/__init__.py",
    "tests/test_sprint_06_4a_3_3_governance_cli.py",
    "tests/test_sprint_06_4a_3_3_import_audit.py",
    "tests/test_sprint_06_4a_3_3_replay_coverage_resume_duckdb.py",
    "tests/test_sprint_06_4a_3_3_schema_plan_writer.py",
    "tests/test_sprint_06_4a_3_3_semantic_pack_cli.py",
    "tests/test_sprint_06_4a_3_material_behaviors.py",
    "tests/test_sprint_06_behavior_coverage_material_nodes.py",
]
EXPECTED_ACCEPTED = [
    "#71/#74/#75/#76",
    "#77/#78/#79/#80",
    "#81/#82/#83/#84",
    "#87/#88/#89/#90",
    "#91/#92/#93/#94",
    "#104+#105/#106/#107/#108",
    "#110/#111/#112/#113",
    "#115/#116/#117/#118",
    "#120/#121/#122/#123",
    "#125/#126/#127/#128",
    "#135+#139+#140/#141/#142/#143",
]
EXPECTED_QUARANTINED = ["#67", "#68", "#95-#103", "#136-#138"]
EXPECTED_RESIDUAL = {
    "129": "corrected deterministic archive lifecycle",
    "131": "canonical acquisition/E2E/scoring/risk umbrella",
    "133": "full-history secret/export hygiene",
    "148": "sink-safe redaction",
    "149": "strict API response envelopes",
    "150": "native grid validate result semantics",
    "151": "prefix-invariant actionable decisions",
    "152": "complete unique universe snapshots",
    "153": "quarantine legacy raw readiness",
    "154": "remove minimum investment as risk authority",
    "155": "reference/fast range config parity",
    "156": "persisted exclusive outcome end in walk-forward",
    "157": "committed-key preflight safety",
    "158": "exact outcome completeness and provenance",
    "159": "import failure cleanup and recovery",
    "160": "retire padded 06.4A.3 evidence",
    "161": "canonical ReplaySlice to OHLC adapter",
}
EXPECTED_DISPOSITION_ISSUES = {
    "#1-#5": [148, 149],
    "#6-#13": [150, 152, 153, 154, 131, 133],
    "#14-#18": [151, 155, 131],
    "#19-#27": [158, 131],
    "#28-#35": [156, 158, 131],
    "#36-#42": [131],
    "#43-#50": [161, 131],
    "#51-#58": [131],
    "#59-#66": [157, 159, 160, 161, 131],
}
EXPECTED_COMPONENT_CLASSES = {
    "C01": "SUPERSEDED_GOVERNED",
    "C02": "CURRENT_UNPROVEN",
    "C03": "CURRENT_UNPROVEN",
    "C04": "LEGACY_NONCANONICAL",
    "C05": "OBSOLETE",
    "C06": "CURRENT_UNPROVEN",
    "C07": "CURRENT_UNPROVEN",
    "C08": "LEGACY_NONCANONICAL",
    "C09": "CURRENT_UNPROVEN",
    "C10": "CURRENT_UNPROVEN",
    "C11": "CURRENT_UNPROVEN",
    "C12": "CURRENT_UNPROVEN",
    "C13": "CURRENT_PROVEN_BOUNDED",
    "C14": "CURRENT_PROVEN_BOUNDED",
    "C15": "CURRENT_PROVEN_BOUNDED",
    "C16": "SUPERSEDED_GOVERNED",
    "C17": "CURRENT_UNPROVEN",
    "C18": "QUARANTINED_EVIDENCE",
    "C19": "CURRENT_UNPROVEN",
}
EXPECTED_SLICE_RANGES = (
    (1, 5, "signing_transport_redaction"),
    (6, 13, "pagination_quality_universe_validate"),
    (14, 35, "range_outcome_scoring"),
    (36, 50, "neutral_grid_ohlc"),
    (51, 66, "public_batch_market_store"),
)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _matrix() -> tuple[str, dict[str, Any]]:
    try:
        raw = (ROOT / MATRIX_PATH).read_bytes().decode("utf-8", "strict")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(SENTINEL) from exc
    visible = HTML_COMMENT.sub("", raw)
    required_headings = (
        "# Pre-control-plane assurance matrix",
        "## Scope, source, and verdict",
        "## Component classifications",
        "## Current path dispositions and bounded truth",
        "## Governed supersession and quarantine",
        "## Residual bounded owners",
        "## Frozen machine manifest",
        "## Fail-closed conclusion",
    )
    fences = JSON_FENCE.findall(visible)
    if (
        not raw.startswith(MARKER + "\n")
        or len(visible) < 60_000
        or any(heading not in visible for heading in required_headings)
        or len(fences) != 1
    ):
        raise RuntimeError(SENTINEL)
    try:
        manifest = json.loads(fences[0], object_pairs_hook=_reject_duplicate_keys)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(SENTINEL) from exc
    if not isinstance(manifest, dict):
        raise RuntimeError(SENTINEL)
    return visible, manifest


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _prose(text: str) -> str:
    return JSON_FENCE.sub("", text)


def _pairs(text: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for key, value in PAIR.findall(_prose(text)):
        result.setdefault(key, set()).add(value)
    return result


def _all_historical_paths(manifest: dict[str, Any]) -> set[str]:
    return {path for row in manifest["prs"] for path in row["changed_paths"]}


def test_matrix_identity_and_authoritative_source_are_frozen() -> None:
    text, manifest = _matrix()
    assert set(manifest) == EXPECTED_TOP_LEVEL
    assert manifest["audit_ref"] == AUDIT_REF
    assert TASK_ID in text and COMMENT_ID in text


def test_machine_manifest_is_exact_authoritative_inventory() -> None:
    _text, manifest = _matrix()
    assert hashlib.sha256(_canonical(manifest)).hexdigest() == MANIFEST_SHA256


def test_read_only_method_and_safety_facts_are_exact() -> None:
    _text, manifest = _matrix()
    assert manifest["method"] == EXPECTED_METHOD
    assert all(
        type(value) is bool and value is False for value in EXPECTED_METHOD.values()
    )


def test_pr_rows_are_atomic_complete_and_ordered() -> None:
    _text, manifest = _matrix()
    rows = manifest["prs"]
    assert len(rows) == 66
    assert [row["pr"] for row in rows] == list(range(1, 67))
    assert all(type(row["pr"]) is int for row in rows)


def test_pr_titles_are_nonempty_exact_and_unique() -> None:
    _text, manifest = _matrix()
    titles = [row["title"] for row in manifest["prs"]]
    assert len(set(titles)) == 66
    assert all(type(title) is str and title.strip() == title for title in titles)
    assert titles[0] == "Implement Sprint 01 API/data feasibility foundation"
    assert titles[-1].startswith("Sprint 06.4A.3.4:")


def test_merge_shas_are_lowercase_exact_and_unique() -> None:
    _text, manifest = _matrix()
    shas = [row["merge_sha"] for row in manifest["prs"]]
    assert len(set(shas)) == 66
    assert all(re.fullmatch(r"[0-9a-f]{40}", sha) for sha in shas)
    assert shas[0] == "fc25e314713b5d2a94e75736d559857884a752cf"
    assert shas[-1] == "ae47603ca34030f6a019a9eeb5d99699bbeee570"


def test_slice_assignments_cover_the_exact_pr_ranges() -> None:
    _text, manifest = _matrix()
    observed = {row["pr"]: row["slice"] for row in manifest["prs"]}
    expected = {
        number: name
        for start, end, name in EXPECTED_SLICE_RANGES
        for number in range(start, end + 1)
    }
    assert observed == expected


def test_each_pr_changed_path_list_is_sorted_unique_and_nonempty() -> None:
    _text, manifest = _matrix()
    for row in manifest["prs"]:
        paths = row["changed_paths"]
        assert paths and paths == sorted(paths)
        assert len(paths) == len(set(paths))
        assert all(type(path) is str and path for path in paths)


def test_historical_path_union_reconciles_exact_counts() -> None:
    _text, manifest = _matrix()
    historical = _all_historical_paths(manifest)
    removed = set(manifest["removed_paths"])
    assert len(historical) == manifest["unique_historical_path_count"] == 280
    assert len(historical - removed) == manifest["surviving_current_path_count"] == 272
    assert len(removed) == 8 and removed <= historical


def test_removed_path_inventory_is_exact_and_absent() -> None:
    _text, manifest = _matrix()
    assert manifest["removed_paths"] == EXPECTED_REMOVED
    assert all(not (ROOT / path).exists() for path in EXPECTED_REMOVED)


def test_surviving_paths_are_contained_current_files() -> None:
    _text, manifest = _matrix()
    surviving = _all_historical_paths(manifest) - set(EXPECTED_REMOVED)
    for path in surviving:
        pure = PurePosixPath(path)
        assert not pure.is_absolute() and ".." not in pure.parts
        assert pure.as_posix() == path
        assert not any(token in path for token in ("*", "?", "#"))
        assert (ROOT / path).is_file(), path


def test_component_rows_are_exact_unique_and_classified() -> None:
    text, _manifest = _matrix()
    rows = COMPONENT_ROW.findall(_prose(text))
    observed = {
        component_id: classification
        for component_id, *_rest, classification, _owner in rows
    }
    assert len(rows) == len(observed) == 19
    assert observed == EXPECTED_COMPONENT_CLASSES
    assert hashlib.sha256(_canonical(rows)).hexdigest() == COMPONENT_ROWS_SHA256


def test_component_vocabulary_contains_every_allowed_disposition() -> None:
    text, _manifest = _matrix()
    prose = _prose(text)
    assert set(EXPECTED_COMPONENT_CLASSES.values()) == {
        "OBSOLETE",
        "SUPERSEDED_GOVERNED",
        "CURRENT_PROVEN_BOUNDED",
        "CURRENT_UNPROVEN",
        "LEGACY_NONCANONICAL",
        "QUARANTINED_EVIDENCE",
    }
    assert all(
        f"`{value}`" in prose for value in set(EXPECTED_COMPONENT_CLASSES.values())
    )


def test_component_evidence_names_real_current_paths() -> None:
    text, _manifest = _matrix()
    required = (
        "src/bybit_grid/bybit/validate_only.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/logging.py",
        "src/bybit_grid/reporting.py",
        "src/bybit_grid/backtest/grid_simulator.py",
        "src/bybit_grid/research/scoring/components.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "src/bybit_grid/data/market_store/reader.py",
        "src/bybit_grid/backtest/ohlc_replay/replay.py",
        "scripts/build_range_candidates.py",
        "scripts/build_candidate_outcomes.py",
    )
    assert all(path in _prose(text) for path in required)
    assert all((ROOT / path).is_file() for path in required)


def test_disposition_spans_and_issue_mappings_are_exact() -> None:
    _text, manifest = _matrix()
    rows = manifest["disposition_summary"]
    observed = {row["historical_prs"]: row["issues"] for row in rows}
    assert len(rows) == 9
    assert observed == EXPECTED_DISPOSITION_ISSUES


def test_disposition_summaries_preserve_bounded_language() -> None:
    _text, manifest = _matrix()
    summaries = "\n".join(row["summary"] for row in manifest["disposition_summary"])
    for phrase in (
        "unproven",
        "legacy",
        "synthetic reference contract proven",
        "offline/mock proven",
        "padded evidence",
    ):
        assert phrase in summaries


def test_accepted_governed_chains_are_exact() -> None:
    text, manifest = _matrix()
    assert manifest["accepted_governed_chains"] == EXPECTED_ACCEPTED
    assert all(chain in _prose(text) for chain in EXPECTED_ACCEPTED)


def test_quarantined_chains_have_no_authority() -> None:
    text, manifest = _matrix()
    assert manifest["quarantined_chains"] == EXPECTED_QUARANTINED
    prose = _prose(text)
    assert all(chain in prose for chain in EXPECTED_QUARANTINED)
    assert "Quarantined\nchains grant no proof" in prose


def test_residual_issue_registry_is_exact_and_atomic() -> None:
    text, manifest = _matrix()
    assert manifest["residual_issues"] == EXPECTED_RESIDUAL
    prose = _prose(text)
    assert all(f"#{number}" in prose for number in EXPECTED_RESIDUAL)


def test_every_new_gap_and_existing_owner_is_tracked() -> None:
    _text, manifest = _matrix()
    residual = {int(number) for number in manifest["residual_issues"]}
    assert residual == {129, 131, 133, *range(148, 162)}
    disposition_issues = {
        issue for row in manifest["disposition_summary"] for issue in row["issues"]
    }
    assert set(range(148, 162)) <= disposition_issues
    assert {131, 133} <= disposition_issues


def test_pr66_padded_material_evidence_is_invalidated() -> None:
    text, _manifest = _matrix()
    prose = _prose(text)
    assert "PR #66 61-row material-coverage claim" in prose
    assert "56 mapped tests are padding/no-op" in prose
    assert "`QUARANTINED_EVIDENCE`" in prose and "#160" in prose


def test_current_proxy_legacy_and_adapter_status_is_truthful() -> None:
    text, _manifest = _matrix()
    prose = _prose(text)
    required = (
        "proxy_only_bool=true",
        "risk_model_status=NOT_YET_PROVEN",
        "risk_budget_proven_bool=false",
        "sufficient_for_parameter_selection_bool=false",
        "runnable, noncanonical, may false-pass",
        "no audited\n  adapter",
    )
    assert all(phrase in prose for phrase in required)


def test_forbidden_capability_truth_pairs_remain_false() -> None:
    text, _manifest = _matrix()
    observed = _pairs(text)
    keys = (
        "issue_134_closeable",
        "implementation_authorized",
        "credentials_authorized",
        "private_api_authorized",
        "public_network_capture_authorized",
        "live_execution_authorized",
        "trading_mutation_authorized",
        "native_equivalence_proven",
        "liquidation_proven",
        "risk_budget_proven",
        "profitability_proven",
        "real_public_completeness_proven",
        "legacy_raw_authoritative",
        "canonical_e2e_proven",
        "general_import_atomicity_proven",
        "parameter_selection_sufficient",
        "live_readiness",
    )
    assert all(observed.get(key) == {"false"} for key in keys)
    prose = re.sub(r"\s+", " ", _prose(text))
    subjects = (
        "credentials?",
        "private API",
        "public network capture",
        "live execution",
        "trading mutation",
        "native equivalence",
        "liquidation",
        "risk budget",
        "profitability",
        "real public completeness",
        "legacy raw",
        "canonical E2E",
        "general import atomicity",
        "parameter selection",
        "live readiness",
    )
    positives = (
        "proven|authorized|available|implemented|enabled|ready|authoritative|sufficient"
    )
    for subject in subjects:
        claim = re.compile(
            rf"\b(?:{subject})\b.{{0,80}}\b(?:{positives})\b",
            re.IGNORECASE,
        )
        for match in claim.finditer(prose):
            assert re.search(
                r"\b(?:not|no|never|false|unproven|unavailable|does not)\b",
                match.group(),
                re.IGNORECASE,
            ), match.group()


def test_issue_134_verdict_stays_open_and_fail_closed() -> None:
    text, _manifest = _matrix()
    prose = _prose(text)
    assert _pairs(text)["issue_134_state"] == {"OPEN"}
    assert "Issue #134 remains open while any\n`CURRENT_UNPROVEN` component" in prose
    assert "mandatory RED closed unmerged" in prose
    assert (
        "grants no credential, network, private API, public capture, live execution"
        in prose
    )
