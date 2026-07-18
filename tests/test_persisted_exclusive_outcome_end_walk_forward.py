from __future__ import annotations

import hashlib
import importlib.util
from io import BytesIO
import json
from pathlib import Path
import zipfile

import polars as pl
import pytest

PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_TEST_CONTRACT = (
    "persisted-exclusive-outcome-end-walk-forward-v1"
)
SENTINEL = "persisted_exclusive_outcome_end_walk_forward_contract_unavailable"
MINUTE_MS = 60_000
DAY_MS = 86_400_000


def _outcome_fields(
    signal_time_ms: int,
    horizon_minutes: int,
    *,
    complete: bool = True,
) -> dict[str, object]:
    entry_time_ms = ((signal_time_ms // MINUTE_MS) + 1) * MINUTE_MS
    return {
        "outcome_semantics_version": "v5_exact_outcome_window_provenance",
        "outcome_window_semantics_version": "exact-minute-outcome-window-v1",
        "actionable_event_semantics_version": "range-actionable-prefix-invariance-v1",
        "decision_time_source": "event_decision_time",
        "causal_provenance_complete_bool": True,
        "decision_time_ms": signal_time_ms,
        "entry_time_ms": entry_time_ms,
        "outcome_end_exclusive_ms": entry_time_ms + horizon_minutes * MINUTE_MS,
        "future_data_complete_bool": complete,
        "future_outcome_eligible_bool": complete,
    }


def _split_row(
    event_id: str,
    signal_time_ms: int,
    horizon_minutes: int,
    *,
    complete: bool = True,
    regime_id: str | None = None,
) -> dict[str, object]:
    return {
        "range_action_event_id": event_id,
        "range_regime_id": regime_id or f"regime_{event_id}",
        "signal_time_ms": signal_time_ms,
        "future_horizon_minutes": horizon_minutes,
        "symbol": "BTCUSDT",
        **_outcome_fields(signal_time_ms, horizon_minutes, complete=complete),
    }


def _grain_frame(signal_time_ms: int = 12_345) -> pl.DataFrame:
    rows = []
    for grid in [5, 10]:
        for sl in [0.0, 1.0]:
            index = len(rows)
            rows.append(
                {
                    "range_action_event_id": "event_1",
                    "range_regime_id": "regime_1",
                    "future_horizon_minutes": 60,
                    "grid_cell_number": grid,
                    "sl_atr_buffer": sl,
                    "outcome_id": f"outcome_{index}",
                    "outcome_match_key": f"match_{index}",
                    "symbol": "BTCUSDT",
                    "category": "linear",
                    "signal_time_ms": signal_time_ms,
                    **_outcome_fields(signal_time_ms, 60),
                }
            )
    return pl.DataFrame(rows)


def _install_small_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    from bybit_grid.research.walk_forward.splits import PROFILES

    monkeypatch.setitem(
        PROFILES,
        "persisted_boundary_test",
        {
            "min_train_days": 1,
            "validation_days": 1,
            "test_days": 1,
            "step_days": 10,
            "purge_minutes": 1,
            "embargo_minutes": 1,
            "max_outcome_horizon_minutes": 1,
        },
    )


def _boundary_events(*, start_ms: int, one_ms_past: bool) -> list[dict[str, object]]:
    train_end = start_ms + DAY_MS
    validation_start = train_end + MINUTE_MS
    validation_end = validation_start + DAY_MS
    test_start = validation_end + MINUTE_MS
    test_end = test_start + DAY_MS
    rows = [_split_row("anchor", start_ms, 1)]
    for role, role_end in [
        ("train", train_end),
        ("validation", validation_end),
        ("test", test_end),
    ]:
        desired_end = role_end + (1 if one_ms_past else 0)
        signal = desired_end - 2 * MINUTE_MS
        rows.append(_split_row(f"{role}_edge", signal, 1))
    rows.append(_split_row("tail", test_end, 1))
    return rows


def _default_history() -> pl.DataFrame:
    return pl.DataFrame(
        [_split_row(f"event_{day}", day * DAY_MS, 2880) for day in range(90)]
    )


def _closure_fixture_module():
    path = Path("tests/test_sprint_05_6_review_pack_closure.py")
    spec = importlib.util.spec_from_file_location("_review_pack_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rewrite_pack(
    source: Path,
    target: Path,
    *,
    parquet_mutations: dict[str, object] | None = None,
    json_mutations: dict[str, object] | None = None,
    manifest_updates: dict[str, object] | None = None,
) -> Path:
    parquet_mutations = parquet_mutations or {}
    json_mutations = json_mutations or {}
    with zipfile.ZipFile(source) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    for name, mutation in parquet_mutations.items():
        frame = pl.read_parquet(BytesIO(members[name]))
        frame = mutation(frame)  # type: ignore[operator]
        buffer = BytesIO()
        frame.write_parquet(buffer)
        members[name] = buffer.getvalue()
    for name, mutation in json_mutations.items():
        payload = json.loads(members[name])
        payload = mutation(payload)  # type: ignore[operator]
        members[name] = json.dumps(payload, sort_keys=True).encode()
    manifest = json.loads(members["review_pack_manifest.json"])
    manifest.update(manifest_updates or {})
    manifest["sha256"] = {
        name: hashlib.sha256(payload).hexdigest()
        for name, payload in members.items()
        if name != "review_pack_manifest.json"
    }
    members["review_pack_manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    with zipfile.ZipFile(target, "w") as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    return target


def _available() -> None:
    marker = "persisted-exclusive-outcome-end-walk-forward-v1"
    production_paths = [
        Path("src/bybit_grid/research/scoring/outcome_grains.py"),
        Path("src/bybit_grid/research/walk_forward/splits.py"),
        Path("src/bybit_grid/research/walk_forward/leakage_audit.py"),
        Path("scripts/check_scoring_review_pack.py"),
        Path("scripts/make_scoring_review_pack.py"),
    ]
    if any(not path.exists() or marker not in path.read_text() for path in production_paths):
        raise RuntimeError(SENTINEL)


def _path_available(path: str) -> bool:
    return Path(path).exists()


def test_contract_versions_and_review_pack_members_are_pinned():
    _available()
    from bybit_grid.research.scoring.outcome_grains import GRAIN_CONTRACT_VERSION
    from bybit_grid.research.walk_forward.splits import OUTCOME_BOUNDARY_SEMANTICS_VERSION
    from scripts.check_scoring_review_pack import REQUIRED

    assert GRAIN_CONTRACT_VERSION == "grain_contract_v4_persisted_exclusive_outcome_end"
    assert OUTCOME_BOUNDARY_SEMANTICS_VERSION == "persisted-exclusive-outcome-end-v1"
    assert len(REQUIRED) == 31
    assert "walk_forward_event_eligibility.parquet" in REQUIRED
    assert "walk_forward_splits.parquet" in REQUIRED
    for path in [
        "src/bybit_grid/research/scoring/outcome_grains.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "src/bybit_grid/research/walk_forward/leakage_audit.py",
        "scripts/check_scoring_review_pack.py",
        "scripts/make_scoring_review_pack.py",
    ]:
        assert PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_TEST_CONTRACT in Path(path).read_text()


def test_grains_preserve_non_aligned_v5_persisted_exclusive_end_without_legacy_alias():
    _available()
    from bybit_grid.research.scoring.outcome_grains import (
        GRAIN_CONTRACT_VERSION,
        build_outcome_grains,
    )

    grains, audit = build_outcome_grains(_grain_frame())
    expected_entry = MINUTE_MS
    expected_end = expected_entry + 60 * MINUTE_MS
    for grain in grains.values():
        assert "outcome_end_exclusive_ms" in grain.columns
        assert "outcome_end_ms" not in grain.columns
        assert grain["entry_time_ms"].unique().to_list() == [expected_entry]
        assert grain["outcome_end_exclusive_ms"].unique().to_list() == [expected_end]
    assert audit["grain_contract_version"] == GRAIN_CONTRACT_VERSION
    assert (
        audit["outcome_boundary_semantics_version"]
        == "persisted-exclusive-outcome-end-v1"
    )
    assert audit["persisted_outcome_end_required_bool"] is True
    assert audit["derived_outcome_end_count"] == 0
    assert audit["legacy_outcome_end_column_allowed_bool"] is False


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("outcome_end_exclusive_ms", None),
        ("outcome_end_exclusive_ms", 3_660_000.0),
        ("outcome_end_exclusive_ms", True),
        ("decision_time_source", "signal_time_fallback"),
        ("causal_provenance_complete_bool", False),
        ("future_outcome_eligible_bool", False),
        ("signal_time_ms", -1),
    ],
)
def test_grains_fail_closed_on_invalid_v5_boundary_contract(column: str, value: object):
    _available()
    from bybit_grid.research.scoring.outcome_grains import build_outcome_grains

    frame = _grain_frame().with_columns(pl.lit(value).alias(column))
    with pytest.raises(ValueError):
        build_outcome_grains(frame)


def test_grains_reject_legacy_alias_and_duplicate_source_provenance():
    _available()
    from bybit_grid.research.scoring.outcome_grains import build_outcome_grains

    base = _grain_frame()
    with pytest.raises(ValueError):
        build_outcome_grains(base.with_columns(pl.lit(0).alias("outcome_end_ms")))
    duplicate = pl.concat([base, base.head(1)], how="vertical")
    with pytest.raises(ValueError):
        build_outcome_grains(duplicate)
    duplicate_id = base.with_columns(
        pl.when(pl.col("grid_cell_number") == 10)
        .then(pl.lit("outcome_0"))
        .otherwise(pl.col("outcome_id"))
        .alias("outcome_id")
    )
    with pytest.raises(ValueError):
        build_outcome_grains(duplicate_id)


def test_split_accepts_exact_persisted_end_at_each_own_role_boundary(
    monkeypatch: pytest.MonkeyPatch,
):
    _available()
    from bybit_grid.research.walk_forward.splits import build_splits

    _install_small_profile(monkeypatch)
    out = build_splits(
        pl.DataFrame(_boundary_events(start_ms=0, one_ms_past=False)),
        "persisted_boundary_test",
    )
    ledger = pl.DataFrame(out.attrs["disposition_ledger"])
    reasons = dict(
        ledger.filter(pl.col("range_action_event_id").str.ends_with("_edge")).select(
            "range_action_event_id", "exclusion_or_assignment_reason"
        ).iter_rows()
    )
    assert reasons == {
        "train_edge": "train_assigned",
        "validation_edge": "validation_assigned",
        "test_edge": "test_assigned",
    }
    for role in ["train", "validation", "test"]:
        row = out.filter(pl.col("range_action_event_id") == f"{role}_edge").row(
            0, named=True
        )
        assert row["outcome_end_exclusive_ms"] == row[f"{role}_end_ms"]


def test_split_excludes_valid_persisted_end_one_ms_past_each_role_boundary(
    monkeypatch: pytest.MonkeyPatch,
):
    _available()
    from bybit_grid.research.walk_forward.splits import build_splits

    _install_small_profile(monkeypatch)
    out = build_splits(
        pl.DataFrame(_boundary_events(start_ms=MINUTE_MS - 1, one_ms_past=True)),
        "persisted_boundary_test",
    )
    ledger = pl.DataFrame(out.attrs["disposition_ledger"])
    edges = ledger.filter(pl.col("range_action_event_id").str.ends_with("_edge"))
    assert dict(
        edges.select("range_action_event_id", "exclusion_or_assignment_reason").iter_rows()
    ) == {
        "train_edge": "train_horizon_boundary",
        "validation_edge": "validation_horizon_boundary",
        "test_edge": "test_horizon_boundary",
    }
    for row in edges.iter_rows(named=True):
        role = row["range_action_event_id"].removesuffix("_edge")
        assert row["outcome_end_exclusive_ms"] == row[f"{role}_end_ms"] + 1


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_canonical_end",
        "legacy_only",
        "duplicate_event_horizon",
        "float_end",
        "boolean_end",
        "wrong_decision_source",
        "eligibility_mismatch",
        "negative_signal",
    ],
)
def test_build_splits_rejects_invalid_or_ambiguous_source_before_classification(
    mutation: str,
):
    _available()
    from bybit_grid.research.walk_forward.splits import build_splits

    row = _split_row("event", DAY_MS, 2880)
    if mutation == "missing_canonical_end":
        row.pop("outcome_end_exclusive_ms")
        frame = pl.DataFrame([row])
    elif mutation == "legacy_only":
        row["outcome_end_ms"] = row.pop("outcome_end_exclusive_ms")
        frame = pl.DataFrame([row])
    elif mutation == "duplicate_event_horizon":
        frame = pl.DataFrame([row, row])
    elif mutation == "float_end":
        row["outcome_end_exclusive_ms"] = float(row["outcome_end_exclusive_ms"])
        frame = pl.DataFrame([row])
    elif mutation == "boolean_end":
        row["outcome_end_exclusive_ms"] = True
        frame = pl.DataFrame([row])
    elif mutation == "wrong_decision_source":
        row["decision_time_source"] = "reconstructed_signal"
        frame = pl.DataFrame([row])
    elif mutation == "eligibility_mismatch":
        row["future_outcome_eligible_bool"] = False
        frame = pl.DataFrame([row])
    else:
        row["signal_time_ms"] = -1
        row.update(_outcome_fields(-1, 2880))
        frame = pl.DataFrame([row])
    with pytest.raises(ValueError):
        build_splits(frame)


def test_schema_less_empty_split_input_does_not_bypass_required_contract():
    _available()
    from bybit_grid.research.walk_forward.splits import build_splits

    with pytest.raises(ValueError):
        build_splits(pl.DataFrame())


def test_missing_and_ineligible_max_horizons_are_distinct_and_universe_is_not_shrunk():
    _available()
    from bybit_grid.research.walk_forward.splits import build_splits

    rows = []
    for day in range(90):
        if day == 0:
            rows.append(_split_row("missing_edge", 0, 60))
        elif day == 89:
            rows.append(_split_row("ineligible_edge", day * DAY_MS, 2880, complete=False))
        else:
            rows.append(_split_row(f"event_{day}", day * DAY_MS, 2880))
    out = build_splits(pl.DataFrame(rows), "prototype_90d")
    ledger = pl.DataFrame(out.attrs["disposition_ledger"])
    first = ledger.filter(pl.col("fold_id") == "wf_000")
    assert first.height == 90
    assert first["range_action_event_id"].n_unique() == 90
    assert first.filter(
        pl.col("exclusion_or_assignment_reason") == "missing_max_horizon"
    )["range_action_event_id"].to_list() == ["missing_edge"]
    assert first.filter(
        pl.col("exclusion_or_assignment_reason") == "ineligible_max_horizon"
    )["range_action_event_id"].to_list() == ["ineligible_edge"]
    missing = first.filter(pl.col("range_action_event_id") == "missing_edge").row(
        0, named=True
    )
    assert missing["future_horizon_minutes"] is None
    assert missing["outcome_end_exclusive_ms"] is None
    assert missing["max_outcome_horizon_minutes"] == 2880
    summary = pl.DataFrame(out.attrs["fold_summary"]).row(0, named=True)
    assert summary["train_start_ms"] == 0
    assert summary["source_event_count"] == 90
    assert summary["missing_max_horizon_count"] == 1
    assert summary["ineligible_max_horizon_count"] == 1
    assert summary["coverage_reconciliation_delta"] == 0
    assert summary["unassigned_event_count"] == 0


def test_write_splits_persists_full_disposition_ledger_and_zero_derivation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _available()
    from bybit_grid.research.walk_forward.splits import write_splits

    monkeypatch.chdir(tmp_path)
    root = Path("data/processed/scoring_runs/run_x")
    root.mkdir(parents=True)
    _default_history().write_parquet(root / "event_horizon.parquet")
    write_splits("run_x")
    ledger = pl.read_parquet(root / "walk_forward_event_eligibility.parquet")
    folds = pl.read_parquet(root / "walk_forward_fold_summary.parquet")
    assert ledger.height == int(folds["source_event_count"].sum())
    assert ledger.height == ledger.select(
        ["fold_id", "range_action_event_id"]
    ).unique().height
    coverage = json.loads((root / "walk_forward_coverage_audit.json").read_text())
    assert coverage["disposition_ledger_reconciliation_ok"] is True
    assert coverage["persisted_outcome_end_required_bool"] is True
    assert coverage["derived_outcome_end_count"] == 0
    assert coverage["legacy_outcome_end_column_allowed_bool"] is False


@pytest.mark.parametrize("role", ["train", "validation", "test"])
def test_leakage_audit_uses_each_roles_own_end_not_the_next_role_start(role: str):
    _available()
    from bybit_grid.research.walk_forward.leakage_audit import audit_splits
    from bybit_grid.research.walk_forward.splits import build_splits

    splits = build_splits(_default_history(), "prototype_90d")
    event_id = splits.filter(pl.col("role") == role)["range_action_event_id"][0]
    end_column = f"{role}_end_ms"
    tampered = splits.with_columns(
        pl.when(pl.col("range_action_event_id") == event_id)
        .then(pl.col(end_column) + 1)
        .otherwise(pl.col("outcome_end_exclusive_ms"))
        .alias("outcome_end_exclusive_ms")
    )
    result = audit_splits(tampered)
    assert result["leakage_audit_ok"] is False
    assert any(v["type"] == f"{role}_outcome_crosses_role_end" for v in result["violations"])


def test_leakage_audit_rejects_duplicate_fold_event_inconsistent_bounds_and_legacy_alias():
    _available()
    from bybit_grid.research.walk_forward.leakage_audit import audit_splits
    from bybit_grid.research.walk_forward.splits import build_splits

    splits = build_splits(_default_history(), "prototype_90d")
    duplicate = pl.concat([splits, splits.head(1)], how="vertical")
    assert any(
        violation["type"] == "duplicate_fold_event_rows"
        for violation in audit_splits(duplicate)["violations"]
    )
    event_id = splits["range_action_event_id"][0]
    inconsistent = splits.with_columns(
        pl.when(pl.col("range_action_event_id") == event_id)
        .then(pl.col("train_end_ms") + 1)
        .otherwise(pl.col("train_end_ms"))
        .alias("train_end_ms")
    )
    assert any(
        violation["type"] == "inconsistent_fold_bounds_or_contract"
        for violation in audit_splits(inconsistent)["violations"]
    )
    legacy = splits.with_columns(pl.lit(0).alias("outcome_end_ms"))
    assert audit_splits(legacy)["leakage_audit_ok"] is False


def test_checker_rejects_coherent_legacy_v4_contract(tmp_path: Path):
    _available()
    from scripts.check_scoring_review_pack import check_zip

    fixture = _closure_fixture_module()
    source = fixture._valid_pack(tmp_path)
    target = tmp_path / "legacy_v4.zip"

    def legacy_grain(payload: dict[str, object]):
        payload["grain_contract_version"] = "grain_contract_v3_whole_row"
        return payload

    def legacy_boundary(payload: dict[str, object]):
        payload["outcome_boundary_semantics_version"] = "derived-signal-end-v0"
        return payload

    _rewrite_pack(
        source,
        target,
        json_mutations={
            "outcome_grain_contract_audit.json": legacy_grain,
            "walk_forward_coverage_audit.json": legacy_boundary,
            "walk_forward_leakage_audit_summary.json": legacy_boundary,
            "walk_forward_temporal_leakage_audit.json": legacy_boundary,
        },
        manifest_updates={
            "review_pack_schema_version": "scoring_review_pack_v4_audit_complete",
            "grain_contract_version": "grain_contract_v3_whole_row",
            "outcome_boundary_semantics_version": "derived-signal-end-v0",
        },
    )
    result = check_zip(str(target), "run_x")
    assert result["review_pack_ok"] is False
    assert "review_pack_schema_version" in result["consistency_errors"]
    assert "manifest_grain_contract_version" in result["consistency_errors"]


def test_checker_recomputes_dispositions_instead_of_trusting_coherently_relabelled_summaries(
    tmp_path: Path,
):
    _available()
    from scripts.check_scoring_review_pack import check_zip

    fixture = _closure_fixture_module()
    source = fixture._valid_pack(tmp_path)
    target = tmp_path / "relabelled.zip"

    def mutate_ledger(frame: pl.DataFrame) -> pl.DataFrame:
        validation_end = frame["validation_end_ms"][0]
        signal = validation_end - 2880 * MINUTE_MS
        entry = ((signal // MINUTE_MS) + 1) * MINUTE_MS
        is_event = pl.col("range_action_event_id") == "e1"
        return frame.with_columns(
            pl.when(is_event).then(pl.lit("purge_gap")).otherwise(
                pl.col("exclusion_or_assignment_reason")
            ).alias("exclusion_or_assignment_reason"),
            pl.when(is_event).then(pl.lit(None).cast(pl.String)).otherwise(
                pl.col("role")
            ).alias("role"),
            pl.when(is_event).then(pl.lit(signal)).otherwise(pl.col("signal_time_ms")).alias(
                "signal_time_ms"
            ),
            pl.when(is_event).then(pl.lit(signal)).otherwise(pl.col("decision_time_ms")).alias(
                "decision_time_ms"
            ),
            pl.when(is_event).then(pl.lit(entry)).otherwise(pl.col("entry_time_ms")).alias(
                "entry_time_ms"
            ),
            pl.when(is_event)
            .then(pl.lit(entry + 2880 * MINUTE_MS))
            .otherwise(pl.col("outcome_end_exclusive_ms"))
            .alias("outcome_end_exclusive_ms"),
        )

    def mutate_reasons(frame: pl.DataFrame) -> pl.DataFrame:
        return frame.with_columns(
            pl.when(pl.col("exclusion_or_assignment_reason") == "validation_assigned")
            .then(pl.lit(0))
            .when(pl.col("exclusion_or_assignment_reason") == "purge_gap")
            .then(pl.lit(1))
            .otherwise(pl.col("event_count"))
            .alias("event_count")
        )

    def mutate_folds(frame: pl.DataFrame) -> pl.DataFrame:
        return frame.with_columns(
            pl.lit(0).alias("validation_events"),
            pl.lit(1).alias("purge_gap_event_count"),
        )

    _rewrite_pack(
        source,
        target,
        parquet_mutations={
            "walk_forward_event_eligibility.parquet": mutate_ledger,
            "walk_forward_exclusion_reason_summary.parquet": mutate_reasons,
            "walk_forward_fold_summary.parquet": mutate_folds,
            "walk_forward_splits.parquet": lambda frame: frame.filter(
                pl.col("range_action_event_id") != "e1"
            ),
        },
    )
    result = check_zip(str(target), "run_x")
    assert result["review_pack_ok"] is False
    assert "walk_forward_disposition_reason_recomputation" in result["consistency_errors"]


def test_checker_rejects_assigned_ledger_split_divergence_even_with_fresh_hashes(
    tmp_path: Path,
):
    _available()
    from scripts.check_scoring_review_pack import check_zip

    fixture = _closure_fixture_module()
    source = fixture._valid_pack(tmp_path)
    target = tmp_path / "split_divergence.zip"
    _rewrite_pack(
        source,
        target,
        parquet_mutations={
            "walk_forward_splits.parquet": lambda frame: frame.filter(
                pl.col("range_action_event_id") != "e2"
            )
        },
    )
    result = check_zip(str(target), "run_x")
    assert result["review_pack_ok"] is False
    assert "walk_forward_assigned_ledger_split_mismatch" in result["consistency_errors"]

    legacy_target = tmp_path / "legacy_ledger_alias.zip"
    _rewrite_pack(
        source,
        legacy_target,
        parquet_mutations={
            "walk_forward_event_eligibility.parquet": lambda frame: frame.with_columns(
                pl.lit(0).alias("outcome_end_ms")
            )
        },
    )
    legacy_result = check_zip(str(legacy_target), "run_x")
    assert legacy_result["review_pack_ok"] is False
    assert (
        "walk_forward_disposition_ledger_legacy_outcome_end_column"
        in legacy_result["consistency_errors"]
    )


def test_maker_declares_v5_contract_and_canonical_boundary_copy_is_lazy_import_safe():
    _available()
    source = Path("scripts/make_scoring_review_pack.py").read_text()
    assert "canonical_boundary_members" in source
    assert "walk_forward_event_eligibility.parquet" in source
    assert "walk_forward_splits.parquet" in source
    assert _path_available("scripts/report_cost_and_scoring.py")
    from scripts.make_scoring_review_pack import (
        PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_CONTRACT as marker,
    )

    assert marker == PERSISTED_EXCLUSIVE_OUTCOME_END_WALK_FORWARD_TEST_CONTRACT
