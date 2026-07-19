from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.check_protected_paths import parse_git_diff_raw_z, protected_path_errors, changed_paths_from_git
from scripts.check_task_scope import (
    ActiveTask,
    acceptance_plan_for_mode,
    frozen_erratum_transition_errors,
    frozen_erratum_v2_transition_errors,
    main as check_task_scope_main,
    classify_pr_mode,
    parse_active_task_bytes,
    parse_frozen_erratum_manifest_bytes,
    parse_frozen_erratum_v2_manifest_bytes,
    parse_labels_json,
    parse_recovery_bundle_manifest_bytes,
    run_exact_recovery_bundle_red,
    pr_mode_scope_errors,
    task_definition_base_path_errors,
    task_definition_head_path_errors,
    task_definition_transition_errors,
    task_scope_errors,
)


def _synthetic_recovery_manifest(root: Path, node_names: tuple[str, ...] = ("test_a", "test_b")):
    from scripts.check_task_scope import RecoveryBundleManifest, RecoveryBundleMember

    test_path = "pm_acceptance/tasks/synthetic/test_contract.py"
    member = RecoveryBundleMember(
        "synthetic", 210, "a" * 40, "b" * 64, test_path, "c" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "d" * 64, (),
        tuple(f"{test_path}::{name}" for name in node_names), "synthetic_contract_unavailable",
    )
    from scripts.check_task_scope import RecoveryErratumV1Evidence, RecoverySuspensionEvidence

    suspension = RecoverySuspensionEvidence("a" * 40, "b" * 40, "c" * 64)
    erratum = RecoveryErratumV1Evidence(
        "d" * 40, "synthetic.json", "e" * 64, test_path, "f" * 64, "100644"
    )
    return RecoveryBundleManifest("synthetic", "synthetic", suspension, erratum, (member,))


def _run_synthetic_recovery_gate(tmp_path: Path, source: str, node_names=("test_a", "test_b")) -> int:
    root = tmp_path / "head"
    test = root / "pm_acceptance/tasks/synthetic/test_contract.py"
    test.parent.mkdir(parents=True)
    test.write_text(source, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    return run_exact_recovery_bundle_red(root, _synthetic_recovery_manifest(root, node_names))


def _build_recovery_bundle_erratum_predecessor_fixture(
    tmp_path: Path,
    *,
    extra_activation_path: bool = False,
):
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo, suspension_sha, erratum_sha, task, _base_test, _head_test = (
        _build_frozen_erratum_repo(
            tmp_path,
            extra_activation_path=extra_activation_path,
        )
    )
    activation_sha = _git(repo, "rev-parse", f"{suspension_sha}^")
    manifest_path = "pm_acceptance/errata/task-a.json"
    test_path = "pm_acceptance/tasks/task-a/test_contract.py"
    contract_path = "docs/frozen_contracts/tasks/task-a.md"

    def committed_bytes(commit_sha: str, path: str) -> bytes:
        return subprocess.run(
            ["git", "show", f"{commit_sha}:{path}"],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        ).stdout

    activation_task = committed_bytes(activation_sha, "pm_acceptance/active_task.json")
    activation_test = committed_bytes(activation_sha, test_path)
    activation_contract = committed_bytes(activation_sha, contract_path)
    suspension_task = committed_bytes(suspension_sha, "pm_acceptance/active_task.json")
    erratum_manifest = committed_bytes(erratum_sha, manifest_path)
    erratum_test = committed_bytes(erratum_sha, test_path)

    member = RecoveryBundleMember(
        task.task_id,
        210,
        activation_sha,
        hashlib.sha256(activation_task).hexdigest(),
        test_path,
        hashlib.sha256(activation_test).hexdigest(),
        contract_path,
        hashlib.sha256(activation_contract).hexdigest(),
        task.required_paths,
        (f"{test_path}::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(
            suspension_sha,
            activation_sha,
            hashlib.sha256(suspension_task).hexdigest(),
        ),
        RecoveryErratumV1Evidence(
            erratum_sha,
            manifest_path,
            hashlib.sha256(erratum_manifest).hexdigest(),
            test_path,
            hashlib.sha256(erratum_test).hexdigest(),
            "100644",
        ),
        (member,),
    )
    return repo, suspension_sha, erratum_sha, manifest


def test_recovery_history_rejects_activation_outside_canonical_first_parent(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "root.txt")
    _git(repo, "commit", "-q", "-m", "root")

    _git(repo, "checkout", "-q", "-b", "activation")
    (repo / "activation.txt").write_text("activation\n", encoding="utf-8")
    _git(repo, "add", "activation.txt")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    (repo / "canonical.txt").write_text("canonical\n", encoding="utf-8")
    _git(repo, "add", "canonical.txt")
    _git(repo, "commit", "-q", "-m", "canonical history")
    _git(repo, "merge", "-q", "--no-ff", "activation", "-m", "merge activation object")
    base_sha = _git(repo, "rev-parse", "HEAD")

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, "a" * 64,
        "pm_acceptance/tasks/synthetic/test_contract.py", "b" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "c" * 64, (),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(base_sha, "e" * 40, "f" * 64),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(base_sha, manifest) == (
            f"recovery_bundle_activation_not_on_first_parent_history:synthetic:{activation_sha}",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_rejects_suspension_outside_canonical_first_parent(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "root.txt")
    _git(repo, "commit", "-q", "-m", "root")

    (repo / "activation.txt").write_text("activation\n", encoding="utf-8")
    _git(repo, "add", "activation.txt")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", "suspension")
    (repo / "suspension.txt").write_text("suspension\n", encoding="utf-8")
    _git(repo, "add", "suspension.txt")
    _git(repo, "commit", "-q", "-m", "task suspension")
    suspension_sha = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "main")
    (repo / "canonical.txt").write_text("canonical\n", encoding="utf-8")
    _git(repo, "add", "canonical.txt")
    _git(repo, "commit", "-q", "-m", "canonical history")
    _git(repo, "merge", "-q", "--no-ff", "suspension", "-m", "merge suspension object")
    base_sha = _git(repo, "rev-parse", "HEAD")

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, "a" * 64,
        "pm_acceptance/tasks/synthetic/test_contract.py", "b" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "c" * 64, (),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(suspension_sha, activation_sha, "d" * 64),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(base_sha, manifest) == (
            f"recovery_bundle_suspension_not_on_first_parent_history:{suspension_sha}",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_exact_suspension_predecessor(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "root.txt")
    _git(repo, "commit", "-q", "-m", "root")
    root_sha = _git(repo, "rev-parse", "HEAD")

    (repo / "activation.txt").write_text("activation\n", encoding="utf-8")
    _git(repo, "add", "activation.txt")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    (repo / "suspension.txt").write_text("suspension\n", encoding="utf-8")
    _git(repo, "add", "suspension.txt")
    _git(repo, "commit", "-q", "-m", "task suspension")
    suspension_sha = _git(repo, "rev-parse", "HEAD")
    base_sha = suspension_sha

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, "a" * 64,
        "pm_acceptance/tasks/synthetic/test_contract.py", "b" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "c" * 64, (),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(suspension_sha, root_sha, "d" * 64),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(base_sha, manifest) == (
            f"recovery_bundle_suspension_predecessor_mismatch:{root_sha}:{activation_sha}",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_suspension_to_change_only_active_task(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    active_path = repo / "pm_acceptance/active_task.json"
    active_path.parent.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "root")

    active_task = _task_bytes(_active_task(task_id="synthetic"))
    active_path.write_bytes(active_task)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(CANONICAL)
    (repo / "unrelated.txt").write_text("not suspension payload\n", encoding="utf-8")
    _git(repo, "add", "pm_acceptance/active_task.json", "unrelated.txt")
    _git(repo, "commit", "-q", "-m", "task suspension")
    suspension_sha = _git(repo, "rev-parse", "HEAD")

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, hashlib.sha256(active_task).hexdigest(),
        "pm_acceptance/tasks/synthetic/test_contract.py", "a" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "b" * 64, ("src/example.py",),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(
            suspension_sha,
            activation_sha,
            hashlib.sha256(CANONICAL).hexdigest(),
        ),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(suspension_sha, manifest) == (
            "recovery_bundle_suspension_changed_paths_mismatch",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_hash_pinned_inactive_suspension_bytes(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    active_path = repo / "pm_acceptance/active_task.json"
    active_path.parent.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "root")

    active_task = _task_bytes(_active_task(task_id="synthetic"))
    active_path.write_bytes(active_task)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "task suspension")
    suspension_sha = _git(repo, "rev-parse", "HEAD")

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, hashlib.sha256(active_task).hexdigest(),
        "pm_acceptance/tasks/synthetic/test_contract.py", "a" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "b" * 64, ("src/example.py",),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(
            suspension_sha,
            activation_sha,
            hashlib.sha256(b"wrong-inactive-task").hexdigest(),
        ),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(suspension_sha, manifest) == (
            "recovery_bundle_suspension_inactive_task_sha256_mismatch",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_canonical_inactive_suspension_task(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    active_path = repo / "pm_acceptance/active_task.json"
    active_path.parent.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "root")

    active_task = _task_bytes(_active_task(task_id="synthetic"))
    active_path.write_bytes(active_task)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    suspension_task = _task_bytes(_active_task(task_id="still-active"))
    active_path.write_bytes(suspension_task)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "task suspension")
    suspension_sha = _git(repo, "rev-parse", "HEAD")

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, hashlib.sha256(active_task).hexdigest(),
        "pm_acceptance/tasks/synthetic/test_contract.py", "a" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "b" * 64, ("src/example.py",),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(
            suspension_sha,
            activation_sha,
            hashlib.sha256(suspension_task).hexdigest(),
        ),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(suspension_sha, manifest) == (
            "recovery_bundle_suspension_task_not_inactive:still-active",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_v1_erratum_as_current_predecessor(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )

    (repo / "ordinary.txt").write_text("ordinary post-erratum commit\n", encoding="utf-8")
    _git(repo, "add", "ordinary.txt")
    _git(repo, "commit", "-q", "-m", "ordinary post-erratum commit")
    base_sha = _git(repo, "rev-parse", "HEAD")

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(base_sha, manifest) == (
            f"recovery_bundle_erratum_not_current_predecessor:{erratum_sha}:{base_sha}",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_rejects_erratum_member_activation_extra_path(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(
            tmp_path,
            extra_activation_path=True,
        )
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(erratum_sha, manifest) == (
            "recovery_bundle_activation_changed_paths_mismatch:task-a",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_suspension_of_current_member(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    activation_sha = manifest.members[-1].activation_commit_sha
    _git(repo, "checkout", "-q", activation_sha)
    active_path = repo / "pm_acceptance/active_task.json"
    active_path.write_bytes(_task_bytes(_active_task(task_id="another-task")))
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "activate another task")
    another_activation_sha = _git(repo, "rev-parse", "HEAD")
    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "inactive base with frozen task")
    rebuilt_suspension_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "cherry-pick", erratum_sha)
    rebuilt_erratum_sha = _git(repo, "rev-parse", "HEAD")

    rebuilt_manifest = replace(
        manifest,
        suspension=replace(
            manifest.suspension,
            commit_sha=rebuilt_suspension_sha,
            predecessor_commit_sha=another_activation_sha,
            inactive_task_sha256=hashlib.sha256(CANONICAL).hexdigest(),
        ),
        erratum_v1=replace(
            manifest.erratum_v1,
            commit_sha=rebuilt_erratum_sha,
            manifest_sha256=hashlib.sha256(
                (repo / manifest.erratum_v1.manifest_path).read_bytes()
            ).hexdigest(),
            corrected_test_sha256=hashlib.sha256(
                (repo / manifest.erratum_v1.corrected_test_path).read_bytes()
            ).hexdigest(),
        ),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            rebuilt_erratum_sha, rebuilt_manifest
        ) == ("recovery_bundle_suspension_predecessor_active_task_mismatch:task-a",)
    finally:
        os.chdir(old_cwd)


def test_recovery_history_rejects_current_member_replay(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    activation_sha = manifest.members[-1].activation_commit_sha
    active_path = repo / "pm_acceptance/active_task.json"
    pinned_active_task = subprocess.run(
        ["git", "show", f"{activation_sha}:pm_acceptance/active_task.json"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout

    _git(repo, "checkout", "-q", activation_sha)
    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "complete current member")
    active_path.write_bytes(pinned_active_task)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "reactivate current member")
    replay_sha = _git(repo, "rev-parse", "HEAD")
    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "suspend replayed current member")
    rebuilt_suspension_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "cherry-pick", erratum_sha)
    rebuilt_erratum_sha = _git(repo, "rev-parse", "HEAD")

    rebuilt_manifest = replace(
        manifest,
        suspension=replace(
            manifest.suspension,
            commit_sha=rebuilt_suspension_sha,
            predecessor_commit_sha=replay_sha,
            inactive_task_sha256=hashlib.sha256(CANONICAL).hexdigest(),
        ),
        erratum_v1=replace(
            manifest.erratum_v1,
            commit_sha=rebuilt_erratum_sha,
            manifest_sha256=hashlib.sha256(
                (repo / manifest.erratum_v1.manifest_path).read_bytes()
            ).hexdigest(),
            corrected_test_sha256=hashlib.sha256(
                (repo / manifest.erratum_v1.corrected_test_path).read_bytes()
            ).hexdigest(),
        ),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            rebuilt_erratum_sha, rebuilt_manifest
        ) == ("recovery_bundle_current_member_replayed:task-a",)
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_erratum_directly_after_suspension(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    _git(repo, "checkout", "-q", suspension_sha)
    intervening_path = repo / "ordinary-between-suspension-and-erratum.txt"
    intervening_path.write_text(
        "ordinary between suspension and erratum\n", encoding="utf-8"
    )
    _git(repo, "add", "ordinary-between-suspension-and-erratum.txt")
    _git(repo, "commit", "-q", "-m", "ordinary between suspension and erratum")
    intervening_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "cherry-pick", erratum_sha)
    base_sha = _git(repo, "rev-parse", "HEAD")
    mutated_manifest = replace(
        manifest,
        erratum_v1=replace(manifest.erratum_v1, commit_sha=base_sha),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            base_sha, mutated_manifest
        ) == (
            f"recovery_bundle_erratum_predecessor_not_suspension:"
            f"{suspension_sha}:{intervening_sha}",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_hash_pinned_v1_erratum_manifest(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    base_sha = erratum_sha
    mutated_manifest = replace(
        manifest,
        erratum_v1=replace(
            manifest.erratum_v1,
            manifest_sha256=hashlib.sha256(b"wrong-v1-manifest").hexdigest(),
        ),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            base_sha, mutated_manifest
        ) == ("recovery_bundle_erratum_manifest_sha256_mismatch",)
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_valid_merged_v1_erratum_transition(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, _erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    manifest_path = repo / "pm_acceptance/errata/task-a.json"
    erratum_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    erratum_manifest["base_sha256"] = hashlib.sha256(b"wrong-v1-base").hexdigest()
    manifest_path.write_text(
        json.dumps(erratum_manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", "pm_acceptance/errata/task-a.json")
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    base_sha = _git(repo, "rev-parse", "HEAD")
    amended_manifest_bytes = manifest_path.read_bytes()
    mutated_manifest = replace(
        manifest,
        erratum_v1=replace(
            manifest.erratum_v1,
            commit_sha=base_sha,
            manifest_sha256=hashlib.sha256(amended_manifest_bytes).hexdigest(),
        ),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            base_sha, mutated_manifest
        ) == ("base_erratum_test_sha256_mismatch",)
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_hash_pinned_v1_corrected_test(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    base_sha = erratum_sha
    mutated_manifest = replace(
        manifest,
        erratum_v1=replace(
            manifest.erratum_v1,
            corrected_test_sha256=hashlib.sha256(b"wrong-corrected-test").hexdigest(),
        ),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            base_sha, mutated_manifest
        ) == ("recovery_bundle_erratum_corrected_test_sha256_mismatch",)
    finally:
        os.chdir(old_cwd)


def test_recovery_history_requires_regular_mode_for_v1_corrected_test(tmp_path: Path):
    from dataclasses import replace

    import scripts.check_task_scope as check_task_scope

    repo, _suspension_sha, _erratum_sha, manifest = (
        _build_recovery_bundle_erratum_predecessor_fixture(tmp_path)
    )
    _git(
        repo,
        "update-index",
        "--chmod=+x",
        "pm_acceptance/tasks/task-a/test_contract.py",
    )
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    base_sha = _git(repo, "rev-parse", "HEAD")
    mutated_manifest = replace(
        manifest,
        erratum_v1=replace(manifest.erratum_v1, commit_sha=base_sha),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(
            base_sha, mutated_manifest
        ) == ("recovery_bundle_erratum_corrected_test_mode_mismatch:100755:100644",)
    finally:
        os.chdir(old_cwd)


def test_recovery_history_rejects_merge_suspension(tmp_path: Path):
    import scripts.check_task_scope as check_task_scope
    from scripts.check_task_scope import (
        RecoveryBundleManifest,
        RecoveryBundleMember,
        RecoveryErratumV1Evidence,
        RecoverySuspensionEvidence,
    )

    repo = tmp_path / "recovery-history"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "root.txt").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "root.txt")
    _git(repo, "commit", "-q", "-m", "root")

    (repo / "activation.txt").write_text("activation\n", encoding="utf-8")
    _git(repo, "add", "activation.txt")
    _git(repo, "commit", "-q", "-m", "member activation")
    activation_sha = _git(repo, "rev-parse", "HEAD")

    _git(repo, "checkout", "-q", "-b", "suspension")
    (repo / "suspension.txt").write_text("suspension\n", encoding="utf-8")
    _git(repo, "add", "suspension.txt")
    _git(repo, "commit", "-q", "-m", "task suspension payload")

    _git(repo, "checkout", "-q", "main")
    _git(repo, "merge", "-q", "--no-ff", "suspension", "-m", "task suspension")
    suspension_sha = _git(repo, "rev-parse", "HEAD")
    base_sha = suspension_sha

    member = RecoveryBundleMember(
        "synthetic", 210, activation_sha, "a" * 64,
        "pm_acceptance/tasks/synthetic/test_contract.py", "b" * 64,
        "docs/frozen_contracts/tasks/synthetic.md", "c" * 64, (),
        ("pm_acceptance/tasks/synthetic/test_contract.py::test_contract",),
        "synthetic_contract_unavailable",
    )
    manifest = RecoveryBundleManifest(
        "pm_recovery_bundle_v1",
        "p0-recovery-walk-forward-committed-key",
        RecoverySuspensionEvidence(suspension_sha, activation_sha, "d" * 64),
        RecoveryErratumV1Evidence(
            "1" * 40, "pm_acceptance/errata/synthetic.json", "2" * 64,
            member.test_path, "3" * 64, "100644",
        ),
        (member,),
    )

    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert check_task_scope.recovery_bundle_history_errors(base_sha, manifest) == (
            f"recovery_bundle_suspension_requires_single_parent:{suspension_sha}",
        )
    finally:
        os.chdir(old_cwd)


def test_recovery_bundle_exact_red_gate_accepts_exact_failed_calls(tmp_path: Path):
    source = (
        "def test_a():\n    raise AssertionError('synthetic_contract_unavailable')\n\n"
        "def test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n"
    )
    assert _run_synthetic_recovery_gate(tmp_path, source) == 0


def test_workflow_recovery_red_uses_only_base_owned_dependency_free_gate():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    step = workflow.split("      - name: Run combined recovery bundle Draft RED\n", 1)[1].split(
        "      - name: Run supplemental PR checks\n", 1
    )[0]
    assert "python ../base/scripts/check_task_scope.py" in step
    assert "--exact-recovery-root ." in step
    assert "--recovery-manifest pm_acceptance/reactivations/" in step
    assert "--json-report" not in step
    assert "python -m pytest" not in step


@pytest.mark.parametrize("mutation", ("duplicate_collection", "duplicate_call", "deselected", "malformed", "subprocess"))
def test_recovery_bundle_exact_red_gate_fails_closed_on_runner_anomalies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
):
    root = tmp_path / "head"
    test = root / "pm_acceptance/tasks/synthetic/test_contract.py"
    test.parent.mkdir(parents=True)
    test.write_text("", encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    manifest = _synthetic_recovery_manifest(root)
    nodes = [node for member in manifest.members for node in member.expected_red_node_ids]

    def fake_run(*args, **kwargs):
        if mutation != "subprocess":
            payload = {
                "calls": [[node, "failed", "synthetic_contract_unavailable"] for node in nodes],
                "collected": list(nodes), "exit_code": 1, "forbidden": [],
            }
            if mutation == "duplicate_collection":
                payload["collected"].append(nodes[0])
            elif mutation == "duplicate_call":
                payload["calls"].append(payload["calls"][0])
            elif mutation == "deselected":
                payload["forbidden"].append(f"deselected:{nodes[0]}")
            elif mutation == "malformed":
                payload = {"calls": "not-a-list"}
            Path(kwargs["env"]["RECOVERY_RESULT"]).write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(args[0], 7 if mutation == "subprocess" else 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_exact_recovery_bundle_red(root, manifest) == 1


@pytest.mark.parametrize(
    ("source", "nodes"),
    (
        ("def test_a():\n    pass\n\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("import pytest\ndef test_a():\n    pytest.skip('no')\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("import pytest\n@pytest.mark.xfail\ndef test_a():\n    raise AssertionError('synthetic_contract_unavailable')\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("import pytest\n@pytest.mark.xfail\ndef test_a():\n    pass\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("import pytest\n@pytest.fixture\ndef bad():\n    raise RuntimeError('setup')\ndef test_a(bad):\n    pass\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("import pytest\n@pytest.fixture\ndef bad():\n    yield\n    raise RuntimeError('teardown')\ndef test_a(bad):\n    raise AssertionError('synthetic_contract_unavailable')\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("raise RuntimeError('collection')\n", ("test_a", "test_b")),
        ("def test_a():\n    raise AssertionError('wrong sentinel')\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("def test_a():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a", "test_b")),
        ("def test_a():\n    raise AssertionError('synthetic_contract_unavailable')\ndef test_b():\n    raise AssertionError('synthetic_contract_unavailable')\n", ("test_a",)),
        ("", ()),
    ),
)
def test_recovery_bundle_exact_red_gate_rejects_outcome_and_collection_anomalies(
    tmp_path: Path, source: str, nodes: tuple[str, ...]
):
    assert _run_synthetic_recovery_gate(tmp_path, source, nodes) == 1


def _recovery_bundle_bytes() -> bytes:
    walk_forward_nodes = [
        "test_contract_markers_exact_scope_and_embedded_source",
        "test_contract_versions_and_review_pack_members_are_pinned",
        "test_grains_preserve_non_aligned_v5_persisted_exclusive_end_without_legacy_alias",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[outcome_end_exclusive_ms-None]",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[outcome_end_exclusive_ms-3660000.0]",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[outcome_end_exclusive_ms-True]",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[decision_time_source-signal_time_fallback]",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[causal_provenance_complete_bool-False]",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[future_outcome_eligible_bool-False]",
        "test_grains_fail_closed_on_invalid_v5_boundary_contract[signal_time_ms--1]",
        "test_grains_reject_legacy_alias_and_duplicate_source_provenance",
        "test_split_accepts_exact_persisted_end_at_each_own_role_boundary",
        "test_split_excludes_valid_persisted_end_one_ms_past_each_role_boundary",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[missing_canonical_end]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[legacy_only]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[duplicate_event_horizon]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[float_end]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[boolean_end]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[wrong_decision_source]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[eligibility_mismatch]",
        "test_build_splits_rejects_invalid_or_ambiguous_source_before_classification[negative_signal]",
        "test_schema_less_empty_split_input_does_not_bypass_required_contract",
        "test_missing_and_ineligible_max_horizons_are_distinct_and_universe_is_not_shrunk",
        "test_write_splits_persists_full_disposition_ledger_and_zero_derivation",
        "test_leakage_audit_uses_each_roles_own_end_not_the_next_role_start[train]",
        "test_leakage_audit_uses_each_roles_own_end_not_the_next_role_start[validation]",
        "test_leakage_audit_uses_each_roles_own_end_not_the_next_role_start[test]",
        "test_leakage_audit_rejects_duplicate_fold_event_inconsistent_bounds_and_legacy_alias",
        "test_checker_rejects_coherent_legacy_v4_contract",
        "test_checker_recomputes_dispositions_instead_of_trusting_coherently_relabelled_summaries",
        "test_checker_rejects_assigned_ledger_split_divergence_even_with_fresh_hashes",
        "test_maker_declares_v5_contract_and_canonical_boundary_copy_is_lazy_import_safe",
    ]
    committed_key_nodes = [
        "test_contract_markers_and_exact_implementation_scope",
        "test_contract_markers_and_exact_public_surface",
        "test_platform_path_reaches_preflight_without_creating_store_root",
        "test_source_hash_revalidation_is_typed_and_prewrite",
        "test_projection_revalidation_rejects_forged_instance",
        "test_exact_accepted_evidence_reimport_is_typed_noop",
        "test_receipt_appearing_after_plan_is_still_exact_typed_noop",
        "test_preflight_rejects_real_different_evidence_key_conflict",
        "test_stale_plan_rechecks_committed_keys_before_transaction_root",
        "test_equal_committed_rows_are_rejected_for_every_dataset[instrument_snapshot]",
        "test_equal_committed_rows_are_rejected_for_every_dataset[trade_kline_1m]",
        "test_equal_committed_rows_are_rejected_for_every_dataset[mark_kline_1m]",
        "test_equal_committed_rows_are_rejected_for_every_dataset[funding_rate]",
        "test_different_committed_rows_are_rejected_for_every_dataset[instrument_snapshot]",
        "test_different_committed_rows_are_rejected_for_every_dataset[trade_kline_1m]",
        "test_different_committed_rows_are_rejected_for_every_dataset[mark_kline_1m]",
        "test_different_committed_rows_are_rejected_for_every_dataset[funding_rate]",
        "test_nonoverlapping_second_import_remains_valid",
        "test_nonexact_existing_receipt_graph_is_not_a_noop",
        "test_conflicting_immutable_chunk_path_fails_before_transaction_root",
    ]
    members = [
        {
            "activation_commit_sha": "1305abb1517944e2cc9790e5546ca52ae66f592e",
            "active_task_sha256": "85e9d288d637d15166da83557ae5462d43a021cc9f6ebc0a3f1b753f8e43597e",
            "contract_path": "docs/frozen_contracts/tasks/p0-walk-forward-exclusive-outcome-end.md",
            "contract_sha256": "6f73875f71defa7c3d6ed824798d795339667391a9860741d3d67f3bf3ec0f05",
            "expected_red_node_ids": [f"pm_acceptance/tasks/p0-walk-forward-exclusive-outcome-end/test_walk_forward_exclusive_outcome_end.py::{node}" for node in walk_forward_nodes],
            "issue_number": 156,
            "required_paths": ["src/bybit_grid/research/scoring/outcome_grains.py", "src/bybit_grid/research/walk_forward/splits.py", "src/bybit_grid/research/walk_forward/leakage_audit.py", "scripts/check_scoring_review_pack.py", "scripts/make_scoring_review_pack.py", "tests/test_sprint_05_cost_scoring_walkforward.py", "tests/test_sprint_05_6_review_pack_closure.py", "tests/test_persisted_exclusive_outcome_end_walk_forward.py"],
            "sentinel": "persisted_exclusive_outcome_end_walk_forward_contract_unavailable",
            "task_id": "p0-walk-forward-exclusive-outcome-end",
            "test_path": "pm_acceptance/tasks/p0-walk-forward-exclusive-outcome-end/test_walk_forward_exclusive_outcome_end.py",
            "test_sha256": "1b77336ba734f0e6b464c9f8304add0c21c707703d800f699f8e68f5e1f4b09e",
        },
        {
            "activation_commit_sha": "3b826f2a6a3b02897047a30de8e920e2f5b72431",
            "active_task_sha256": "248e518d84d7fa43ccc0536145e7d61e2e427df64b5d18825626da872cb15a89",
            "contract_path": "docs/frozen_contracts/tasks/p0-committed-key-preflight.md",
            "contract_sha256": "21cc51b5e8f6ffece6af18f7a6c674309915ca6018dbe9f5011174f72d895696",
            "expected_red_node_ids": [f"pm_acceptance/tasks/p0-committed-key-preflight/test_store_committed_key_preflight.py::{node}" for node in committed_key_nodes],
            "issue_number": 157,
            "required_paths": ["src/bybit_grid/data/market_store/models.py", "src/bybit_grid/data/market_store/import_public_batch.py", "src/bybit_grid/data/market_store/transaction.py", "tests/test_store_committed_key_preflight.py"],
            "sentinel": "committed_key_preflight_contract_unavailable",
            "task_id": "p0-committed-key-preflight",
            "test_path": "pm_acceptance/tasks/p0-committed-key-preflight/test_store_committed_key_preflight.py",
            "test_sha256": "d7734ba1f0f3c42df0927c843c1691003de906ef3ad2cfd8e88ba3ac6512f513",
        },
    ]
    obj = {
        "bundle_id": "p0-recovery-walk-forward-committed-key",
        "erratum_v1": {
            "commit_sha": hashlib.sha1(b"future-156-v1-erratum").hexdigest(),
            "corrected_test_mode": "100644",
            "corrected_test_sha256": hashlib.sha256(b"future-156-corrected-test").hexdigest(),
            "manifest_sha256": hashlib.sha256(b"future-156-v1-manifest").hexdigest(),
        },
        "members": members,
        "schema": "pm_recovery_bundle_v1",
        "suspension": {
            "commit_sha": hashlib.sha1(b"future-157-suspension").hexdigest(),
            "inactive_task_sha256": hashlib.sha256(b"canonical-inactive-task").hexdigest(),
            "predecessor_commit_sha": hashlib.sha1(b"future-157-merged-implementation").hexdigest(),
        },
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_recovery_bundle_manifest_is_canonical_and_exactly_pinned():
    manifest = parse_recovery_bundle_manifest_bytes(_recovery_bundle_bytes())
    assert manifest.bundle_id == "p0-recovery-walk-forward-committed-key"
    assert tuple(member.issue_number for member in manifest.members) == (156, 157)
    assert tuple(len(member.expected_red_node_ids) for member in manifest.members) == (32, 20)
    assert manifest.suspension.predecessor_commit_sha == hashlib.sha1(
        b"future-157-merged-implementation"
    ).hexdigest()
    assert manifest.erratum_v1.manifest_path == (
        "pm_acceptance/errata/p0-walk-forward-exclusive-outcome-end.json"
    )
    assert manifest.erratum_v1.corrected_test_path == (
        "pm_acceptance/tasks/p0-walk-forward-exclusive-outcome-end/"
        "test_walk_forward_exclusive_outcome_end.py"
    )
    assert manifest.erratum_v1.corrected_test_mode == "100644"


def test_recovery_bundle_manifest_rejects_noncanonical_and_substituted_identity():
    with pytest.raises(ValueError, match="^noncanonical_recovery_bundle_bytes$"):
        parse_recovery_bundle_manifest_bytes(json.dumps(json.loads(_recovery_bundle_bytes()), indent=2).encode() + b"\n")
    obj = json.loads(_recovery_bundle_bytes())
    obj["members"][1]["issue_number"] = 158
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^recovery_bundle_identity_mismatch$"):
        parse_recovery_bundle_manifest_bytes(raw)


@pytest.mark.parametrize("mutation", ("missing", "extra", "substituted", "reordered", "duplicate"))
def test_recovery_bundle_manifest_rejects_every_real_node_sequence_mutation(mutation: str):
    obj = json.loads(_recovery_bundle_bytes())
    nodes = obj["members"][0]["expected_red_node_ids"]
    if mutation == "missing":
        nodes.pop()
    elif mutation == "extra":
        nodes.append(nodes[-1] + "_extra")
    elif mutation == "substituted":
        nodes[-1] += "_substituted"
    elif mutation == "reordered":
        nodes[0], nodes[1] = nodes[1], nodes[0]
    else:
        nodes[-1] = nodes[0]
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError):
        parse_recovery_bundle_manifest_bytes(raw)


@pytest.mark.parametrize(
    ("target", "mutation"),
    (
        ("top", "missing"),
        ("top", "unknown"),
        ("suspension", "missing"),
        ("suspension", "unknown"),
        ("erratum_v1", "missing"),
        ("erratum_v1", "unknown"),
        ("suspension", "bool"),
        ("suspension", "short_hash"),
        ("suspension", "uppercase_hash"),
        ("suspension", "zero_hash"),
        ("suspension", "placeholder_hash"),
        ("suspension", "same_commits"),
        ("erratum_v1", "short_hash"),
        ("erratum_v1", "uppercase_hash"),
        ("erratum_v1", "zero_hash"),
        ("erratum_v1", "placeholder_hash"),
        ("erratum_v1", "wrong_mode"),
        ("erratum_v1", "reused_commit"),
    ),
)
def test_recovery_bundle_manifest_rejects_unpinned_future_evidence(
    target: str, mutation: str
):
    obj = json.loads(_recovery_bundle_bytes())
    value = obj if target == "top" else obj[target]
    if mutation == "missing":
        value.pop(next(iter(value)))
    elif mutation == "unknown":
        value["unexpected"] = "value"
    elif mutation == "bool":
        value["commit_sha"] = True
    elif mutation == "short_hash":
        value["commit_sha"] = "a" * 39
    elif mutation == "uppercase_hash":
        value["commit_sha"] = value["commit_sha"].upper()
    elif mutation == "zero_hash":
        key = "inactive_task_sha256" if target == "suspension" else "manifest_sha256"
        value[key] = "0" * 64
    elif mutation == "placeholder_hash":
        key = "inactive_task_sha256" if target == "suspension" else "manifest_sha256"
        value[key] = "a" * 64
    elif mutation == "same_commits":
        value["predecessor_commit_sha"] = value["commit_sha"]
    elif mutation == "wrong_mode":
        value["corrected_test_mode"] = "100755"
    elif mutation == "reused_commit":
        value["commit_sha"] = obj["suspension"]["commit_sha"]
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^invalid_recovery_bundle_"):
        parse_recovery_bundle_manifest_bytes(raw)


@pytest.mark.parametrize(
    "raw",
    (
        b"{\"bundle_id\":\"x\",\"bundle_id\":\"y\"}\n",
        b"{",
        b"\xef\xbb\xbf{}\n",
        b"{\"value\":1.5}\n",
        b"{\"value\":NaN}\n",
        b"\xff\n",
    ),
)
def test_recovery_bundle_manifest_decoder_failures_are_stable(raw: bytes):
    with pytest.raises(ValueError, match="^invalid_recovery_bundle_json$"):
        parse_recovery_bundle_manifest_bytes(raw)


def test_recovery_bundle_manifest_rejects_wrong_scope_order_and_member_order():
    for mutate in (
        lambda obj: obj["members"].reverse(),
        lambda obj: obj["members"][0]["required_paths"].reverse(),
        lambda obj: obj["members"][0]["required_paths"].append("src/extra.py"),
        lambda obj: obj["members"][1]["required_paths"].__setitem__(
            0, obj["members"][0]["required_paths"][0]
        ),
    ):
        obj = json.loads(_recovery_bundle_bytes())
        mutate(obj)
        raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        with pytest.raises(ValueError, match="^recovery_bundle_identity_mismatch$"):
            parse_recovery_bundle_manifest_bytes(raw)


def test_recovery_bundle_transition_requires_exact_previous_member_base(monkeypatch):
    import scripts.check_task_scope as check_task_scope

    manifest_bytes = _recovery_bundle_bytes()
    manifest = parse_recovery_bundle_manifest_bytes(manifest_bytes)
    base_sha = "a" * 40
    head_sha = "b" * 40
    previous_member = manifest.members[0]
    previous_member_task = _active_task(
        task_id=previous_member.task_id,
        allowed_paths=previous_member.required_paths,
        required_paths=previous_member.required_paths,
    )
    union_scope = tuple(
        path for member in manifest.members for path in member.required_paths
    )
    head_task = _active_task(
        task_id=manifest.bundle_id,
        allowed_paths=union_scope,
        required_paths=union_scope,
    )
    manifest_path = f"pm_acceptance/reactivations/{manifest.bundle_id}.json"

    historical_hashes = {
        (member.activation_commit_sha, path): expected_hash
        for member in manifest.members
        for path, expected_hash in (
            (member.test_path, member.test_sha256),
            (member.contract_path, member.contract_sha256),
            ("pm_acceptance/active_task.json", member.active_task_sha256),
        )
    }

    def future_manifest_and_historical_blobs(ref: str, path: str) -> bytes:
        if ref == head_sha and path == manifest_path:
            return manifest_bytes
        return historical_hashes[(ref, path)].encode()

    real_sha256 = check_task_scope._sha256

    def pinned_historical_hash(data: bytes) -> str:
        if len(data) == 64:
            return data.decode("ascii")
        return real_sha256(data)

    def one_parent_rev_list(args, **_kwargs):
        assert args == ["git", "rev-list", "--parents", "-n", "1", head_sha]
        return subprocess.CompletedProcess(args, 0, stdout=f"{head_sha} {base_sha}\n")

    monkeypatch.setattr(
        check_task_scope, "git_blob_from_ref", future_manifest_and_historical_blobs
    )
    monkeypatch.setattr(check_task_scope, "git_object_exists", lambda *_: False)
    monkeypatch.setattr(check_task_scope, "_sha256", pinned_historical_hash)
    monkeypatch.setattr(check_task_scope.subprocess, "run", one_parent_rev_list)
    monkeypatch.setattr(check_task_scope, "recovery_bundle_history_errors", lambda *_: ())
    changed_paths = ("pm_acceptance/active_task.json", manifest_path)

    assert check_task_scope.recovery_bundle_transition_errors(
        base_sha, head_sha, previous_member_task, head_task, changed_paths
    ) == ()
    assert check_task_scope.recovery_bundle_transition_errors(
        base_sha, head_sha, parse_active_task_bytes(CANONICAL), head_task, changed_paths
    ) == (
        "recovery_bundle_base_task_not_previous_member:"
        "p0-walk-forward-exclusive-outcome-end",
    )


CANONICAL = json.dumps({
    "schema": "pm_active_task_v1",
    "task_id": "NO_ACTIVE_IMPLEMENTATION",
    "allowed_paths": [],
    "required_paths": [],
    "forbidden_paths": [
        "AGENTS.md", ".github/CODEOWNERS", ".github/workflows/**", ".github/actions/**",
        "pm_acceptance/**", "docs/frozen_contracts/**", "scripts/check_protected_paths.py",
        "scripts/check_task_scope.py", "scripts/check_numeric_environment.py", "scripts/check_no_live_execution.py",
        "conftest.py", "pytest.ini", "setup.py", "setup.cfg", "tox.ini", "noxfile.py",
        "sitecustomize.py", "usercustomize.py", "sitecustomize/**", "usercustomize/**",
        "src/sitecustomize.py", "src/usercustomize.py", "src/sitecustomize/**", "src/usercustomize/**",
        "pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements/*.txt",
        "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock",
    ],
}, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _active_task(
    task_id: str = "task-a",
    allowed_paths: tuple[str, ...] = ("src/**",),
    required_paths: tuple[str, ...] = ("src/example.py",),
) -> ActiveTask:
    return ActiveTask(
        "pm_active_task_v1",
        task_id,
        allowed_paths,
        required_paths,
        parse_active_task_bytes(CANONICAL).forbidden_paths,
    )


def _task_bytes(task: ActiveTask) -> bytes:
    return json.dumps(
        {
            "allowed_paths": list(task.allowed_paths),
            "forbidden_paths": list(task.forbidden_paths),
            "required_paths": list(task.required_paths),
            "schema": task.schema,
            "task_id": task.task_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"


def _erratum_bytes(
    *,
    task: ActiveTask,
    base_test: bytes,
    head_test: bytes,
    test_path: str = "pm_acceptance/tasks/task-a/test_contract.py",
    failed: tuple[str, ...] | None = None,
    passed: tuple[str, ...] = (),
    issue_number: int = 98,
    reason_code: str = "invalid_deterministic_fixture",
    historical_active_task_commit_sha: str = "1" * 40,
) -> bytes:
    if failed is None:
        failed = (f"{test_path}::test_contract",)
    obj = {
        "base_sha256": hashlib.sha256(base_test).hexdigest(),
        "expected_red_failed_node_ids": list(failed),
        "expected_red_passed_node_ids": list(passed),
        "head_active_task_sha256": hashlib.sha256(_task_bytes(task)).hexdigest(),
        "head_sha256": hashlib.sha256(head_test).hexdigest(),
        "historical_active_task_commit_sha": historical_active_task_commit_sha,
        "issue_number": issue_number,
        "reason_code": reason_code,
        "schema": "pm_frozen_erratum_v1",
        "task_id": task.task_id,
        "test_path": test_path,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _erratum_v2_bytes(
    *,
    task: ActiveTask,
    base_test: bytes,
    head_test: bytes,
    predecessor_manifest: bytes,
    predecessor_commit_sha: str,
    test_path: str = "pm_acceptance/tasks/task-a/test_contract.py",
    failed: tuple[str, ...] | None = None,
    passed: tuple[str, ...] = (),
    issue_number: int = 98,
    reason_code: str = "invalid_isolated_import_fixture",
    historical_active_task_commit_sha: str = "1" * 40,
) -> bytes:
    if failed is None:
        failed = (f"{test_path}::test_contract",)
    obj = {
        "base_sha256": hashlib.sha256(base_test).hexdigest(),
        "expected_red_failed_node_ids": list(failed),
        "expected_red_passed_node_ids": list(passed),
        "head_active_task_sha256": hashlib.sha256(_task_bytes(task)).hexdigest(),
        "head_sha256": hashlib.sha256(head_test).hexdigest(),
        "historical_active_task_commit_sha": historical_active_task_commit_sha,
        "issue_number": issue_number,
        "predecessor_commit_sha": predecessor_commit_sha,
        "predecessor_manifest_sha256": hashlib.sha256(predecessor_manifest).hexdigest(),
        "reason_code": reason_code,
        "schema": "pm_frozen_erratum_v2",
        "task_id": task.task_id,
        "test_path": test_path,
    }
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def test_safe_unprotected_source_file_accepted():
    assert protected_path_errors(("src/example.py",)) == ()


def test_exact_protected_file_rejected():
    assert protected_path_errors(("AGENTS.md",)) == ("protected_path_changed:AGENTS.md",)


def test_nested_pm_acceptance_rejected():
    assert protected_path_errors(("pm_acceptance/test_x.py",)) == ("protected_path_changed:pm_acceptance/test_x.py",)


def test_nested_docs_frozen_contracts_rejected():
    assert protected_path_errors(("docs/frozen_contracts/x.md",)) == ("protected_path_changed:docs/frozen_contracts/x.md",)


def test_backslash_path_rejected():
    assert protected_path_errors((r"src\x.py",)) == (r"unsafe_path:src\x.py",)


def test_absolute_path_rejected():
    assert protected_path_errors(("/src/x.py",)) == ("unsafe_path:/src/x.py",)


def test_dotdot_component_rejected():
    assert protected_path_errors(("src/../x.py",)) == ("unsafe_path:src/../x.py",)


def test_control_character_path_rejected():
    assert protected_path_errors(("src/bad\nname.py",)) == ("unsafe_path:src/bad\nname.py",)


def test_duplicate_changed_path_rejected():
    assert protected_path_errors(("src/x.py", "src/x.py")) == ("duplicate_path:src/x.py",)


def test_valid_canonical_inactive_task_parses():
    task = parse_active_task_bytes(CANONICAL)
    assert task.task_id == "NO_ACTIVE_IMPLEMENTATION"


def test_committed_task_is_canonical_and_keeps_mandatory_forbidden_rules():
    task_file = Path(__file__).with_name("active_task.json")
    committed = parse_active_task_bytes(task_file.read_bytes())
    mandatory = set(parse_active_task_bytes(CANONICAL).forbidden_paths)
    assert committed.schema == "pm_active_task_v1"
    assert mandatory.issubset(committed.forbidden_paths)


def test_duplicate_json_key_rejected():
    with pytest.raises(ValueError, match="^duplicate_json_key:schema$"):
        parse_active_task_bytes(b'{"schema":"x","schema":"x"}\n')


def test_float_token_rejected():
    with pytest.raises(ValueError, match="^float_token:1.0$"):
        parse_active_task_bytes(b'{"allowed_paths":1.0}\n')


def test_unknown_task_key_rejected():
    data = dict(json.loads(CANONICAL))
    data["extra"] = "x"
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^invalid_task_keys:missing=:unknown=extra$"):
        parse_active_task_bytes(raw)


def test_noncanonical_task_bytes_rejected():
    with pytest.raises(ValueError, match="^noncanonical_task_bytes$"):
        parse_active_task_bytes(json.dumps(json.loads(CANONICAL), indent=2).encode() + b"\n")


def test_inactive_task_rejects_implementation_source_change():
    task = parse_active_task_bytes(CANONICAL)
    assert task_scope_errors(task, ("src/x.py",)) == ("no_active_implementation_task:src/x.py",)


def test_active_task_accepts_allowed_exact_file():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/x.py",), (), ())
    assert task_scope_errors(task, ("src/x.py",)) == ()


def test_active_task_accepts_allowed_prefix():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ())
    assert task_scope_errors(task, ("src/pkg/x.py",)) == ()


def test_active_task_rejects_out_of_scope_file():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ())
    assert task_scope_errors(task, ("docs/x.md",)) == ("out_of_scope_path:docs/x.md",)


def test_forbidden_rule_wins_over_allowed_rule():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), (), ("src/secret.py",))
    assert task_scope_errors(task, ("src/secret.py",)) == ("forbidden_path_changed:src/secret.py",)


def test_missing_required_path_rejected():
    task = ActiveTask("pm_active_task_v1", "TASK", ("src/**",), ("src/required.py",), ())
    assert task_scope_errors(task, ("src/other.py",)) == ("required_path_missing:src/required.py",)


def test_json_lists_are_converted_to_immutable_tuples():
    task = parse_active_task_bytes(CANONICAL)
    assert isinstance(task.allowed_paths, tuple)
    assert isinstance(task.required_paths, tuple)
    assert isinstance(task.forbidden_paths, tuple)


def test_dependency_paths_are_protected_with_exact_errors():
    assert protected_path_errors(("pyproject.toml",)) == ("protected_path_changed:pyproject.toml",)
    assert protected_path_errors(("uv.lock",)) == ("protected_path_changed:uv.lock",)
    assert protected_path_errors(("requirements/base.txt",)) == ("protected_path_changed:requirements/base.txt",)


def test_src_customization_paths_are_protected_with_exact_errors():
    assert protected_path_errors(("src/sitecustomize.py",)) == ("protected_path_changed:src/sitecustomize.py",)
    assert protected_path_errors(("src/usercustomize.py",)) == ("protected_path_changed:src/usercustomize.py",)
    assert protected_path_errors(("sitecustomize/__init__.py",)) == (
        "protected_path_changed:sitecustomize/__init__.py",
    )
    assert protected_path_errors(("usercustomize/__init__.py",)) == (
        "protected_path_changed:usercustomize/__init__.py",
    )
    assert protected_path_errors(("src/sitecustomize/__init__.py",)) == (
        "protected_path_changed:src/sitecustomize/__init__.py",
    )
    assert protected_path_errors(("src/usercustomize/__init__.py",)) == (
        "protected_path_changed:src/usercustomize/__init__.py",
    )


def test_broad_src_task_still_rejects_startup_hook_packages():
    task = _active_task(required_paths=())
    assert pr_mode_scope_errors(
        task,
        ("src/sitecustomize/__init__.py",),
        actor="codex",
        labels=(),
    ) == (
        "forbidden_path_changed:src/sitecustomize/__init__.py",
        "protected_path_changed:src/sitecustomize/__init__.py",
    )
    assert pr_mode_scope_errors(
        task,
        ("src/usercustomize/__init__.py",),
        actor="codex",
        labels=(),
    ) == (
        "forbidden_path_changed:src/usercustomize/__init__.py",
        "protected_path_changed:src/usercustomize/__init__.py",
    )


def test_no_required_commands_or_shell_command_field_exists():
    task = parse_active_task_bytes(CANONICAL)
    assert not hasattr(task, "required_commands")
    data = dict(json.loads(CANONICAL))
    data["required_commands"] = []
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^invalid_task_keys:missing=:unknown=required_commands$"):
        parse_active_task_bytes(raw)


def test_output_mode_for_all_valid_modes():
    assert classify_pr_mode("codex", (), ("src/x.py",))[0] == "implementation"
    assert classify_pr_mode(
        "brullik",
        ("pm-task-definition",),
        ("pm_acceptance/active_task.json", "pm_acceptance/tasks/task-a/test_x.py"),
    )[0] == "pm-task-definition"
    assert classify_pr_mode("brullik", ("pm-control-plane",), ("AGENTS.md",))[0] == "pm-control-plane"
    assert classify_pr_mode(
        "brullik",
        ("pm-frozen-erratum",),
        (
            "pm_acceptance/active_task.json",
            "pm_acceptance/errata/task-a.json",
            "pm_acceptance/tasks/task-a/test_x.py",
        ),
    )[0] == "pm-frozen-erratum"


def test_pm_recovery_bundle_classifies_exact_owner_two_path_payload():
    assert classify_pr_mode(
        "brullik",
        ("pm-recovery-bundle",),
        (
            "pm_acceptance/active_task.json",
            "pm_acceptance/reactivations/p0-recovery-walk-forward-committed-key.json",
        ),
    ) == ("pm-recovery-bundle", ())


def test_mode_acceptance_plan_selection():
    assert acceptance_plan_for_mode("implementation") == ("base-isolated-acceptance",)
    assert acceptance_plan_for_mode("pm-control-plane") == (
        "base-control-plane-self-tests",
        "head-control-plane-self-tests",
    )
    assert acceptance_plan_for_mode("pm-task-definition") == ("base-control-plane-self-tests", "head-task-definition-collect-only")
    assert acceptance_plan_for_mode("pm-frozen-erratum") == (
        "base-control-plane-self-tests",
        "head-frozen-erratum-exact-red",
    )
    assert acceptance_plan_for_mode("pm-recovery-bundle") == (
        "base-control-plane-self-tests",
        "head-recovery-bundle-exact-red",
    )


def test_recovery_bundle_rejects_extra_label_even_when_payload_is_exact():
    paths = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/reactivations/p0-recovery-walk-forward-committed-key.json",
    )
    assert classify_pr_mode("brullik", ("pm-recovery-bundle", "documentation"), paths)[1] == (
        "pm_recovery_bundle_requires_exactly_one_label",
    )


def test_pr_mode_labels_and_scope_fail_closed():
    task_path = "pm_acceptance/tasks/task-a/test_x.py"
    assert classify_pr_mode("alice", ("pm-task-definition",), (task_path,))[1] == (
        "wrong_author:alice",
    )
    assert classify_pr_mode(
        "brullik",
        ("pm-task-definition", "pm-control-plane"),
        (task_path,),
    )[1] == ("multiple_mode_labels",)
    assert classify_pr_mode("brullik", ("pm-unknown",), ("src/x.py",))[1] == ("unknown_mode_label:pm-unknown",)
    assert classify_pr_mode("brullik", (), ("pm_acceptance/x.py",))[1] == ("missing_required_mode_label:pm_acceptance/x.py",)
    assert classify_pr_mode("brullik", ("pm-task-definition",), ("src/x.py",))[1] == (
        "pm_task_definition_out_of_scope:src/x.py",
        "production_path_forbidden_in_pm_mode:src/x.py",
    )
    assert classify_pr_mode("brullik", ("pm-control-plane",), ("AGENTS.md",))[1] == ()
    assert classify_pr_mode(
        "brullik",
        ("pm-frozen-erratum",),
        ("src/example.py",),
    )[1] == (
        "pm_frozen_erratum_out_of_scope:src/example.py",
        "production_path_forbidden_in_pm_mode:src/example.py",
    )


def test_comma_containing_label_cannot_select_privileged_mode():
    labels = parse_labels_json('["note,pm-task-definition"]')
    mode, errors = classify_pr_mode(
        "brullik",
        labels,
        ("pm_acceptance/active_task.json",),
    )
    assert mode == "implementation"
    assert errors == ("missing_required_mode_label:pm_acceptance/active_task.json",)


def test_labels_json_rejects_duplicates_and_non_strings():
    with pytest.raises(ValueError, match="^duplicate_label:pm-task-definition$"):
        parse_labels_json('["pm-task-definition","pm-task-definition"]')
    with pytest.raises(ValueError, match="^label_not_string$"):
        parse_labels_json('[1]')


def test_canonical_frozen_erratum_manifest_parses_exact_evidence():
    task = _active_task()
    base_test = b"def test_contract():\n    assert False\n"
    head_test = b"HELPER = 1\n\ndef test_contract():\n    assert False\n"
    manifest = parse_frozen_erratum_manifest_bytes(
        _erratum_bytes(
            task=task,
            base_test=base_test,
            head_test=head_test,
            passed=("pm_acceptance/tasks/task-a/test_contract.py::test_compatibility",),
        )
    )
    assert manifest.schema == "pm_frozen_erratum_v1"
    assert manifest.task_id == "task-a"
    assert manifest.issue_number == 98
    assert manifest.historical_active_task_commit_sha == "1" * 40
    assert manifest.reason_code == "invalid_deterministic_fixture"
    assert manifest.expected_red_failed_node_ids == (
        "pm_acceptance/tasks/task-a/test_contract.py::test_contract",
    )


def test_frozen_erratum_manifest_is_strict_canonical_and_typed():
    task = _active_task()
    base_test = b"def test_contract():\n    assert False\n"
    head_test = b"X = 1\n" + base_test
    canonical = _erratum_bytes(task=task, base_test=base_test, head_test=head_test)
    with pytest.raises(ValueError, match="^noncanonical_erratum_bytes$"):
        parse_frozen_erratum_manifest_bytes(
            json.dumps(json.loads(canonical), indent=2).encode() + b"\n"
        )
    bad_issue = dict(json.loads(canonical))
    bad_issue["issue_number"] = True
    with pytest.raises(ValueError, match="^invalid_erratum_issue_number$"):
        parse_frozen_erratum_manifest_bytes(
            json.dumps(bad_issue, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
    bad_sha = dict(json.loads(canonical))
    bad_sha["head_sha256"] = "A" * 64
    with pytest.raises(ValueError, match="^invalid_erratum_head_sha256$"):
        parse_frozen_erratum_manifest_bytes(
            json.dumps(bad_sha, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )
    bad_historical = dict(json.loads(canonical))
    bad_historical["historical_active_task_commit_sha"] = "A" * 40
    with pytest.raises(
        ValueError,
        match="^invalid_erratum_historical_active_task_commit_sha$",
    ):
        parse_frozen_erratum_manifest_bytes(
            json.dumps(bad_historical, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        )


def test_frozen_erratum_manifest_rejects_ambiguous_red_outcomes():
    task = _active_task()
    base_test = b"def test_contract():\n    assert False\n"
    head_test = b"X = 1\n" + base_test
    node_id = "pm_acceptance/tasks/task-a/test_contract.py::test_contract"
    overlap = _erratum_bytes(
        task=task,
        base_test=base_test,
        head_test=head_test,
        failed=(node_id,),
        passed=(node_id,),
    )
    with pytest.raises(ValueError, match="^red_node_id_outcome_overlap:"):
        parse_frozen_erratum_manifest_bytes(overlap)
    empty = dict(json.loads(overlap))
    empty["expected_red_failed_node_ids"] = []
    empty["expected_red_passed_node_ids"] = []
    raw = json.dumps(empty, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^expected_red_failed_node_ids_empty$"):
        parse_frozen_erratum_manifest_bytes(raw)


def test_canonical_frozen_erratum_v2_manifest_is_strict_and_chained():
    task = _active_task()
    first_test = b'FIXTURE = b"first"\n\ndef test_contract():\n    assert False\n'
    second_test = first_test.replace(b'FIXTURE = b"first"', b'FIXTURE = b"second"')
    predecessor = _erratum_bytes(
        task=task,
        base_test=b'FIXTURE = b"broken"\n\ndef test_contract():\n    assert False\n',
        head_test=first_test,
    )
    raw = _erratum_v2_bytes(
        task=task,
        base_test=first_test,
        head_test=second_test,
        predecessor_manifest=predecessor,
        predecessor_commit_sha="2" * 40,
    )
    manifest = parse_frozen_erratum_v2_manifest_bytes(raw)
    assert manifest.schema == "pm_frozen_erratum_v2"
    assert manifest.predecessor_commit_sha == "2" * 40
    assert manifest.predecessor_manifest_sha256 == hashlib.sha256(predecessor).hexdigest()
    assert manifest.base_sha256 == hashlib.sha256(first_test).hexdigest()

    with pytest.raises(ValueError, match="^noncanonical_erratum_v2_bytes$"):
        parse_frozen_erratum_v2_manifest_bytes(
            json.dumps(json.loads(raw), indent=2).encode() + b"\n"
        )
    bad = dict(json.loads(raw))
    bad["predecessor_commit_sha"] = "A" * 40
    bad_raw = json.dumps(bad, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(ValueError, match="^invalid_erratum_v2_predecessor_commit_sha$"):
        parse_frozen_erratum_v2_manifest_bytes(bad_raw)
    bad = dict(json.loads(raw))
    bad["predecessor_manifest_sha256"] = "0" * 63
    bad_raw = json.dumps(bad, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    with pytest.raises(
        ValueError,
        match="^invalid_erratum_v2_predecessor_manifest_sha256$",
    ):
        parse_frozen_erratum_v2_manifest_bytes(bad_raw)


def test_v1_manifest_parser_and_path_cannot_be_reused_as_v2():
    task = _active_task()
    base_test = b"def test_contract():\n    assert False\n"
    head_test = b"HELPER = 1\n" + base_test
    v1 = _erratum_bytes(task=task, base_test=base_test, head_test=head_test)
    with pytest.raises(ValueError, match="^invalid_erratum_v2_keys:"):
        parse_frozen_erratum_v2_manifest_bytes(v1)


def test_frozen_erratum_requires_owner_and_label_for_protected_payload():
    paths = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/errata/task-a.json",
        "pm_acceptance/tasks/task-a/test_contract.py",
    )
    assert classify_pr_mode("alice", ("pm-frozen-erratum",), paths)[1] == (
        "wrong_author:alice",
    )
    assert classify_pr_mode("brullik", (), paths)[1] == tuple(
        f"missing_required_mode_label:{path}" for path in paths
    )


def test_pm_task_definition_cannot_modify_frozen_control_plane_files():
    assert classify_pr_mode(
        "brullik",
        ("pm-task-definition",),
        ("pm_acceptance/test_control_plane_self.py",),
    )[1] == ("pm_task_definition_out_of_scope:pm_acceptance/test_control_plane_self.py",)
    assert classify_pr_mode(
        "brullik",
        ("pm-task-definition",),
        ("pm_acceptance/conftest.py",),
    )[1] == ("pm_task_definition_out_of_scope:pm_acceptance/conftest.py",)


@pytest.mark.parametrize(
    "path",
    ("pm_acceptance/active_task.json", "pm_acceptance/conftest.py"),
)
def test_pm_control_plane_cannot_change_task_state_or_acceptance_conftest(path: str):
    assert classify_pr_mode("brullik", ("pm-control-plane",), (path,))[1] == (
        f"pm_control_plane_out_of_scope:{path}",
    )


def test_pm_task_definition_rejects_task_local_conftest():
    path = "pm_acceptance/tasks/task-a/conftest.py"
    assert classify_pr_mode("brullik", ("pm-task-definition",), (path,))[1] == (
        f"task_local_conftest_forbidden:{path}",
    )


def test_open_task_transition_accepts_matching_isolated_layout():
    base = parse_active_task_bytes(CANONICAL)
    head = _active_task()
    changed = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/tasks/task-a/test_contract.py",
        "docs/frozen_contracts/tasks/task-a.md",
    )
    assert task_definition_transition_errors(base, head, changed) == ()


def test_open_task_transition_rejects_task_id_path_mismatch():
    base = parse_active_task_bytes(CANONICAL)
    head = _active_task()
    changed = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/tasks/task-b/test_contract.py",
    )
    assert task_definition_transition_errors(base, head, changed) == (
        "task_id_path_mismatch:pm_acceptance/tasks/task-b/test_contract.py",
        "task_test_missing:task-a",
    )


def test_open_task_transition_requires_changed_task_test():
    base = parse_active_task_bytes(CANONICAL)
    head = _active_task()
    changed = (
        "pm_acceptance/active_task.json",
        "docs/frozen_contracts/tasks/task-a.md",
    )
    assert task_definition_transition_errors(base, head, changed) == (
        "task_test_missing:task-a",
    )


def test_open_task_transition_rejects_unsafe_task_id():
    base = parse_active_task_bytes(CANONICAL)
    head = _active_task(task_id="Task_A")
    changed = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/tasks/Task_A/test_contract.py",
    )
    assert task_definition_transition_errors(base, head, changed) == (
        "unsafe_task_id:Task_A",
    )


def test_open_task_transition_requires_nonempty_covered_rules():
    base = parse_active_task_bytes(CANONICAL)
    empty = _active_task(allowed_paths=(), required_paths=())
    changed = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/tasks/task-a/test_contract.py",
    )
    assert task_definition_transition_errors(base, empty, changed) == (
        "open_task_allowed_paths_empty",
        "open_task_required_paths_empty",
    )
    uncovered = _active_task(allowed_paths=("src/a/**",), required_paths=("src/b.py",))
    assert task_definition_transition_errors(base, uncovered, changed) == (
        "required_rule_not_allowed:src/b.py",
    )
    impossible = ActiveTask(
        "pm_active_task_v1",
        "task-a",
        ("src/**",),
        ("src/example.py",),
        (*parse_active_task_bytes(CANONICAL).forbidden_paths, "src/**"),
    )
    assert task_definition_transition_errors(base, impossible, changed) == (
        "required_rule_forbidden:src/example.py",
    )


def test_open_task_transition_rejects_protected_allowed_and_required_rules():
    base = parse_active_task_bytes(CANONICAL)
    head = _active_task(
        allowed_paths=("src/sitecustomize/**",),
        required_paths=("src/sitecustomize/__init__.py",),
    )
    changed = (
        "pm_acceptance/active_task.json",
        "pm_acceptance/tasks/task-a/test_contract.py",
    )
    assert task_definition_transition_errors(base, head, changed) == (
        "protected_allowed_rule:src/sitecustomize/**",
        "protected_required_rule:src/sitecustomize/__init__.py",
        "required_rule_forbidden:src/sitecustomize/__init__.py",
    )


def test_close_task_transition_is_separate_and_exact():
    base = _active_task()
    head = parse_active_task_bytes(CANONICAL)
    assert task_definition_transition_errors(
        base,
        head,
        ("pm_acceptance/active_task.json",),
    ) == ()
    assert task_definition_transition_errors(
        base,
        head,
        ("pm_acceptance/active_task.json", "pm_acceptance/tasks/task-a/test_contract.py"),
    ) == ("close_task_extra_path:pm_acceptance/tasks/task-a/test_contract.py",)


def test_head_active_task_noncanonical_bytes_rejected():
    with pytest.raises(ValueError, match="^noncanonical_task_bytes$"):
        parse_active_task_bytes(json.dumps(json.loads(CANONICAL), indent=2).encode() + b"\n")


def test_workflow_collects_only_the_head_task_id_directory():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    assert "task-id: ${{ steps.scope.outputs.task_id }}" in workflow
    assert 'head/pm_acceptance/tasks/$TASK_ID' in workflow
    assert 'task_path="$HEAD_ACCEPTANCE_TEMP/pm_acceptance/tasks/$TASK_ID"' in workflow
    assert 'cp -R head/pm_acceptance "$RUNNER_TEMP/head_task_definition/pm_acceptance"' not in workflow


def test_workflow_control_plane_mode_checks_base_and_head_without_running_frozen_tasks():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    base_acceptance = workflow.split("      - name: Run base isolated acceptance harness\n", 1)[1].split(
        "      - name: Run base control-plane self-tests for PM-owned PRs\n",
        1,
    )[0]
    base_control = workflow.split(
        "      - name: Run base control-plane self-tests for PM-owned PRs\n",
        1,
    )[1].split("      - name: Stage head control-plane self-tests\n", 1)[0]
    head_control = workflow.split("      - name: Stage head control-plane self-tests\n", 1)[1].split(
        "      - name: Stage head task-definition acceptance tree\n",
        1,
    )[0]
    supplemental = workflow.split("      - name: Run supplemental PR checks\n", 1)[1].split(
        "\n  status-final:",
        1,
    )[0]

    assert "pr-mode == 'implementation'" in base_acceptance
    assert "pr-mode != 'implementation'" in base_control
    assert "base/scripts/check_task_scope.py" in base_control
    assert "--exact-control-plane-root" in base_control
    assert head_control.count("pr-mode == 'pm-control-plane'") == 3
    assert 'cp head/pm_acceptance/test_control_plane_self.py' in head_control
    assert 'cp head/pm_acceptance/active_task.json' in head_control
    assert "cp -R head/pm_acceptance" not in head_control
    assert "conftest.py" not in head_control
    assert "head/pm_acceptance/tasks" not in head_control
    assert "base/scripts/check_task_scope.py" in head_control
    assert "--exact-control-plane-root" in head_control
    assert 'require "psych"; Psych.parse_file' in head_control
    assert 'if [ "$PR_MODE" = "implementation" ]; then' in supplemental
    assert "python -m pytest tests -q" in supplemental
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD: '1'" in supplemental


def test_workflow_pins_security_critical_trigger_and_base_classifier_shape():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    protected = workflow.split("\n  protected-paths:\n", 1)[1].split("\n  acceptance:\n", 1)[0]
    acceptance = workflow.split("\n  acceptance:\n", 1)[1].split("\n  status-final:\n", 1)[0]

    assert (
        "types: [opened, synchronize, reopened, ready_for_review, converted_to_draft, labeled, unlabeled]"
        in workflow
    )
    assert "group: pm-acceptance-${{ github.event.pull_request.number }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "permissions:\n  contents: read\n  pull-requests: read" in workflow
    assert "ref: ${{ github.event.pull_request.base.sha }}" in protected
    assert "persist-credentials: false" in protected
    assert 'git fetch --no-tags origin "$HEAD_SHA"' in protected
    assert "github.event.pull_request.head.sha" in protected
    assert "statuses: write" not in protected
    assert "statuses: write" not in acceptance


def _run_exact_control_plane_gate(
    tmp_path: Path,
    *,
    conftest: str | None = None,
    test_source: str = "def test_plain_pass():\n    assert True\n",
) -> subprocess.CompletedProcess[str]:
    root = tmp_path / "exact-control"
    acceptance = root / "pm_acceptance"
    acceptance.mkdir(parents=True)
    (acceptance / "test_control_plane_self.py").write_text(
        test_source,
        encoding="utf-8",
    )
    if conftest is not None:
        (acceptance / "conftest.py").write_text(conftest, encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    checker = Path(__file__).resolve().parents[1] / "scripts/check_task_scope.py"
    return subprocess.run(
        [
            sys.executable,
            str(checker),
            "--exact-control-plane-root",
            str(root),
        ],
        env=dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_exact_control_plane_gate_accepts_nonempty_plain_passes(tmp_path: Path):
    result = _run_exact_control_plane_gate(tmp_path)
    assert result.returncode == 0
    assert '"collected_count":1' in result.stdout
    assert '"errors":[]' in result.stdout
    assert '"passed_count":1' in result.stdout


def test_exact_control_plane_gate_rejects_conftest_skip_padding(tmp_path: Path):
    result = _run_exact_control_plane_gate(
        tmp_path,
        conftest=(
            "import pytest\n\n"
            "def pytest_collection_modifyitems(items):\n"
            "    for item in items:\n"
            "        item.add_marker(pytest.mark.skip(reason='padding'))\n"
        ),
    )
    assert result.returncode == 1
    assert "skipped:" in result.stdout
    assert "plain-pass-set-mismatch" in result.stdout


def test_exact_control_plane_gate_rejects_early_success_process_exit(tmp_path: Path):
    result = _run_exact_control_plane_gate(
        tmp_path,
        test_source=(
            "import os\n\n"
            "def test_plain_pass():\n"
            "    os._exit(0)\n"
        ),
    )
    assert result.returncode == 1
    assert "control-plane-self-runner-failed:0" in result.stdout


def test_workflow_publishes_fail_closed_aggregate_status_on_pr_head():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    pending = workflow.split("\n  status-pending:\n", 1)[1].split("\n  protected-paths:\n", 1)[0]
    acceptance = workflow.split("\n  acceptance:\n", 1)[1].split("\n  status-final:\n", 1)[0]
    final = workflow.split("\n  status-final:\n", 1)[1]

    assert workflow.count("statuses: write") == 2
    assert workflow.count('"context": "pm-acceptance"') == 2
    assert pending.count("github.event.pull_request.head.sha") == 1
    assert final.count("github.event.pull_request.head.sha") == 1
    assert pending.count('"brullik/bybit-grid-research"') == 1
    assert final.count('"brullik/bybit-grid-research"') == 1
    assert pending.count("timeout-minutes: 2") == 1
    assert final.count("timeout-minutes: 2") == 1
    assert "actions/checkout" not in pending
    assert "actions/checkout" not in final
    assert "statuses: write" not in acceptance
    assert "needs: [status-pending, protected-paths, acceptance]" in final
    assert 'upstream_success = all(result == "success" for result in results.values())' in final
    assert 'ready = os.environ["PR_DRAFT"] == "false"' in final
    assert 'owner_authored = os.environ["PR_AUTHOR"] == "brullik"' in final
    assert 'non_probe = not os.environ["HEAD_REF"].startswith("probe/")' in final
    assert "successful = upstream_success and ready and owner_authored and non_probe" in final
    assert 'elif upstream_success or any(result == "failure" for result in results.values())' in final
    assert 'state = "error"' in final
    assert 'summary[:140]' in final
    assert 'raise SystemExit("pm_acceptance_failed")' in final


def test_workflow_aggregate_status_write_jobs_never_execute_pr_head_code():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    pending = workflow.split("\n  status-pending:\n", 1)[1].split("\n  protected-paths:\n", 1)[0]
    final = workflow.split("\n  status-final:\n", 1)[1]

    for status_job in (pending, final):
        assert "statuses: write" in status_job
        assert "contents: read" not in status_job
        assert "actions/checkout" not in status_job
        assert "\n      - uses:" not in status_job
        assert "working-directory:" not in status_job
        assert "pull_request.head.repo" not in status_job
        assert "secrets." not in status_job
        assert "artifact" not in status_job
        assert "cache" not in status_job
        assert "urllib.request.urlopen" in status_job

    assert "converted_to_draft" in workflow


def test_workflow_stages_sha_pinned_frozen_erratum_and_requires_exact_red_outcomes():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    stage = workflow.split("      - name: Stage SHA-pinned head frozen erratum\n", 1)[1].split(
        "      - name: Run corrected head erratum and verify exact RED manifest\n",
        1,
    )[0]
    execute = workflow.split(
        "      - name: Run corrected head erratum and verify exact RED manifest\n",
        1,
    )[1].split("      - name: Run supplemental PR checks\n", 1)[0]
    supplemental = workflow.split("      - name: Run supplemental PR checks\n", 1)[1].split(
        "\n  status-final:",
        1,
    )[0]

    assert '"pm-frozen-erratum"' in workflow
    assert "pr-mode == 'implementation'" in workflow
    assert "pr-mode == 'pm-frozen-erratum'" in workflow
    assert 'v1_manifest_path = Path("head/pm_acceptance/errata") / f"{task_id}.json"' in stage
    assert 'base_source = Path("base") / Path(*test_path.parts)' in stage
    assert 'head_source = Path("head") / Path(*test_path.parts)' in stage
    assert 'Path("head/pm_acceptance/active_task.json").read_bytes()' in stage
    assert 'manifest["base_sha256"]' in stage
    assert 'manifest["head_sha256"]' in stage
    assert 'manifest["head_active_task_sha256"]' in stage
    assert "shutil.copyfile(base_source, destination_base_test)" in stage
    assert "shutil.copyfile(head_source, destination_head_test)" in stage
    assert 'normal_root = destination_root / "normal_suite"' in stage
    assert 'shutil.copytree(Path("base/pm_acceptance"), normal_root / "pm_acceptance")' in stage
    assert '(normal_scripts / "__init__.py").write_text("", encoding="utf-8")' in stage
    assert "cp -R head/pm_acceptance" not in stage
    assert 'head_result["exit_code"] != 1' in execute
    assert "forbidden_outcomes=" in execute
    assert "failed_node_ids_mismatch" in execute
    assert "passed_node_ids_mismatch" in execute
    assert "expected_node_ids_vs_base_collection_mismatch" in execute
    assert "head_outcome_union_vs_base_collection_mismatch" in execute
    assert "subprocess.run(" in execute
    assert "report.when != \"call\"" in execute
    assert "report.failed or report.skipped" in execute
    assert 'raise SystemExit("invalid_v1_normal_staged_scripts")' in execute
    assert '(normal_suite,)' in execute
    assert '"PYTHONPATH": os.pathsep.join(str(path) for path in python_path)' in execute
    assert '"RUNNER_TEMP": str(suite_root)' in execute
    assert 'if [ "$PR_MODE" = "implementation" ]; then' in supplemental
    assert "python -m pytest tests -q" in supplemental


def test_workflow_v2_chains_predecessor_and_uses_normal_isolated_import_order():
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    stage = workflow.split("      - name: Stage SHA-pinned head frozen erratum\n", 1)[1].split(
        "      - name: Run corrected head erratum and verify exact RED manifest\n",
        1,
    )[0]
    execute = workflow.split(
        "      - name: Run v2 corrected head under normal isolated import order\n",
        1,
    )[1].split("      - name: Run supplemental PR checks\n", 1)[0]

    assert 'v2_manifest_path = Path("head/pm_acceptance/errata") / f"{task_id}.v2.json"' in stage
    assert 'expected_schema = f"pm_frozen_erratum_{erratum_version}"' in stage
    assert '"predecessor_commit_sha"' in stage
    assert '"predecessor_manifest_sha256"' in stage
    assert 'Path("base/pm_acceptance/errata") / f"{task_id}.json"' in stage
    assert 'predecessor.get("issue_number") != manifest["issue_number"]' in stage
    assert '"merge-base",' in stage
    assert 'git_show(f"pm_acceptance/errata/{task_id}.json") != predecessor_raw' in stage
    assert 'git_show("pm_acceptance/active_task.json")' in stage
    assert 'shutil.copytree(Path("base/pm_acceptance"), normal_root / "pm_acceptance")' in stage
    assert '(normal_scripts / "__init__.py").write_text("", encoding="utf-8")' in stage
    assert 'Path("base/scripts/check_protected_paths.py")' in stage
    assert 'Path("base/scripts/check_task_scope.py")' in stage

    assert "steps.erratum-stage.outputs.erratum_version == 'v2'" in execute
    assert '"RUNNER_TEMP": str(suite_root)' in execute
    assert '(base_suite, Path(os.environ["TRUSTED_BASE"]))' in execute
    assert '(normal_suite,)' in execute
    assert '(staged_scripts / "__init__.py").read_bytes() != b""' in execute
    assert 'if report.outcome != "passed"' in execute
    assert 'f"non-call-{report.when}-{report.outcome}:{report.nodeid}"' in execute
    assert 'f"missing-call:{node_id}"' in execute
    assert 'f"call-not-collected:{node_id}"' in execute
    assert "v2_expected_node_ids_vs_base_collection_mismatch" in execute
    assert "v2_head_vs_base_collection_mismatch" in execute
    assert "v2_head_outcome_union_vs_base_collection_mismatch" in execute
    assert "v2_failed_node_ids_mismatch" in execute
    assert "v2_passed_node_ids_mismatch" in execute
    assert '"status": "exact-v2-red-manifest-matched"' in execute


def _execute_v2_exact_outcome_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    head_source: str,
) -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    execute = workflow.split(
        "      - name: Run v2 corrected head under normal isolated import order\n",
        1,
    )[1].split("      - name: Run supplemental PR checks\n", 1)[0]
    source = textwrap.dedent(
        execute.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    )
    root = tmp_path / "v2-runner"
    test_path = Path("pm_acceptance/tasks/task-a/test_contract.py")
    base_suite = root / "base_suite"
    normal_suite = root / "normal_suite"
    base_test = base_suite / test_path
    head_test = normal_suite / test_path
    base_test.parent.mkdir(parents=True)
    head_test.parent.mkdir(parents=True)
    baseline_source = (
        "def test_contract():\n"
        "    assert False\n\n"
        "def test_compatibility():\n"
        "    assert True\n"
    )
    base_test.write_text(baseline_source)
    head_test.write_text(head_source)
    (base_suite / "pytest.ini").write_text("[pytest]\n")
    (normal_suite / "pytest.ini").write_text("[pytest]\n")
    scripts = normal_suite / "scripts"
    scripts.mkdir()
    (scripts / "__init__.py").write_bytes(b"")
    (scripts / "check_protected_paths.py").write_text("")
    (scripts / "check_task_scope.py").write_text("")
    manifest_path = root / "pm_acceptance/errata/task-a.v2.json"
    manifest_path.parent.mkdir(parents=True)
    prefix = test_path.as_posix()
    manifest_path.write_text(json.dumps({
        "schema": "pm_frozen_erratum_v2",
        "expected_red_failed_node_ids": [f"{prefix}::test_contract"],
        "expected_red_passed_node_ids": [f"{prefix}::test_compatibility"],
    }))
    trusted = root / "trusted-base"
    trusted.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setenv("ERRATUM_MANIFEST", "pm_acceptance/errata/task-a.v2.json")
    monkeypatch.setenv("ERRATUM_TEST_PATH", prefix)
    monkeypatch.setenv("TRUSTED_BASE", str(trusted))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    exec(compile(source, "pm-acceptance-v2-outcome-gate", "exec"), {})


def test_workflow_v2_outcome_gate_accepts_exact_failed_and_passed_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    _execute_v2_exact_outcome_workflow(
        tmp_path,
        monkeypatch,
        (
            "def test_contract():\n"
            "    assert False\n\n"
            "def test_compatibility():\n"
            "    assert True\n"
        ),
    )
    assert '"status":"exact-v2-red-manifest-matched"' in capsys.readouterr().out


@pytest.mark.parametrize(
    ("head_source", "expected"),
    (
        (
            "import pytest\n\n"
            "@pytest.fixture\n"
            "def broken():\n"
            "    raise RuntimeError('setup')\n\n"
            "def test_contract(broken):\n"
            "    assert False\n\n"
            "def test_compatibility():\n"
            "    assert True\n",
            "non-call-setup-failed",
        ),
        (
            "import pytest\n\n"
            "@pytest.fixture\n"
            "def broken():\n"
            "    yield\n"
            "    raise RuntimeError('teardown')\n\n"
            "def test_contract(broken):\n"
            "    assert False\n\n"
            "def test_compatibility():\n"
            "    assert True\n",
            "non-call-teardown-failed",
        ),
        (
            "import pytest\n\n"
            "def test_contract():\n"
            "    pytest.skip('not a call outcome')\n\n"
            "def test_compatibility():\n"
            "    assert True\n",
            "call-skipped",
        ),
        (
            "import pytest\n\n"
            "@pytest.mark.xfail\n"
            "def test_contract():\n"
            "    assert False\n\n"
            "def test_compatibility():\n"
            "    assert True\n",
            "xfail-or-xpass",
        ),
    ),
)
def test_workflow_v2_outcome_gate_rejects_every_non_call_or_non_plain_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    head_source: str,
    expected: str,
):
    with pytest.raises(SystemExit, match=expected):
        _execute_v2_exact_outcome_workflow(tmp_path, monkeypatch, head_source)


def _execute_final_status_script(monkeypatch, **overrides: str) -> tuple[str | None, dict[str, str]]:
    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/pm-acceptance.yml").read_text()
    final = workflow.split("\n  status-final:\n", 1)[1]
    source = textwrap.dedent(
        final.split("          python - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
    )
    environment = {
        "GH_TOKEN": "test-token",
        "HEAD_SHA": "a" * 40,
        "REPOSITORY": "brullik/bybit-grid-research",
        "API_URL": "https://api.example.test",
        "SERVER_URL": "https://example.test",
        "RUN_ID": "123",
        "PENDING_RESULT": "success",
        "PROTECTED_RESULT": "success",
        "ACCEPTANCE_RESULT": "success",
        "PR_AUTHOR": "brullik",
        "PR_DRAFT": "false",
        "HEAD_REF": "pm/task-a",
        "BASE_REF": "main",
        "BASE_SHA": "b" * 40,
        "EVENT_NAME": "pull_request_target",
        "EVENT_ACTION": "synchronize",
        "PR_SENDER": "brullik",
    }
    environment.update(overrides)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    captured: dict[str, str] = {}

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(request, timeout):
        assert timeout == 30
        captured.update(json.loads(request.data))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    exit_reason = None
    try:
        exec(compile(source, "pm-acceptance-finalizer", "exec"), {})
    except SystemExit as exc:
        exit_reason = str(exc)
    return exit_reason, captured


def test_final_status_script_succeeds_only_for_ready_owner_non_probe(monkeypatch):
    exit_reason, payload = _execute_final_status_script(monkeypatch)
    assert exit_reason is None
    assert payload["state"] == "success"
    assert payload["context"] == "pm-acceptance"
    assert payload["target_url"].endswith("/actions/runs/123")

    for ineligible, expected_exit in (
        ({"PR_DRAFT": "true"}, "pm_acceptance_failed"),
        ({"PR_AUTHOR": "someone-else"}, "invalid_live_owner_identity"),
        ({"HEAD_REF": "probe/task-a-red"}, "pm_acceptance_failed"),
    ):
        exit_reason, payload = _execute_final_status_script(monkeypatch, **ineligible)
        assert exit_reason == expected_exit
        if expected_exit == "pm_acceptance_failed":
            assert payload["state"] == "failure"


def test_final_status_script_distinguishes_failure_from_cancelled(monkeypatch):
    exit_reason, payload = _execute_final_status_script(monkeypatch, PROTECTED_RESULT="failure")
    assert exit_reason == "pm_acceptance_failed"
    assert payload["state"] == "failure"

    exit_reason, payload = _execute_final_status_script(monkeypatch, ACCEPTANCE_RESULT="cancelled")
    assert exit_reason == "pm_acceptance_failed"
    assert payload["state"] == "error"


def test_direct_task_scope_cli_import_shape_from_repository_root():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_task_scope.py", "--help"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0
    assert "--task-file" in result.stdout
    assert result.stderr == ""


def test_parse_raw_diff_rejects_symlink_and_submodule_modes():
    symlink = b":000000 120000 0000000 1111111 A\0link\0"
    submodule = b":000000 160000 0000000 1111111 A\0module\0"
    assert parse_git_diff_raw_z(symlink)[1] == ("unsupported_git_diff_mode:120000",)
    assert parse_git_diff_raw_z(submodule)[1] == ("unsupported_git_diff_mode:160000",)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout.strip()


def _build_frozen_erratum_repo(
    tmp_path: Path,
    *,
    base_test: bytes | None = None,
    head_test: bytes | None = None,
    manifest_transform=None,
    extra_activation_path: bool = False,
) -> tuple[Path, str, str, ActiveTask, bytes, bytes]:
    repo = tmp_path / "erratum-repo"
    test_path = repo / "pm_acceptance/tasks/task-a/test_contract.py"
    contract_path = repo / "docs/frozen_contracts/tasks/task-a.md"
    active_path = repo / "pm_acceptance/active_task.json"
    test_path.parent.mkdir(parents=True)
    contract_path.parent.mkdir(parents=True)
    if base_test is None:
        base_test = (
            b'FIXTURE = b"invalid"\n\n'
            b"def helper():\n    return FIXTURE\n\n"
            b"def test_contract():\n    assert helper()\n\n"
            b"def test_compatibility():\n    assert True\n"
        )
    if head_test is None:
        head_test = base_test.replace(b'FIXTURE = b"invalid"', b'FIXTURE = b"valid-zip"')
    active_path.parent.mkdir(parents=True, exist_ok=True)
    task = _active_task()
    active_path.write_bytes(CANONICAL)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "canonical inactive root")

    active_path.write_bytes(_task_bytes(task))
    test_path.write_bytes(base_test)
    contract_path.write_text("# Frozen task\n")
    if extra_activation_path:
        (repo / "unrelated.txt").write_text("unrelated activation path\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "historical active task")
    historical_active = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "inactive base with frozen task")
    base = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(_task_bytes(task))
    test_path.write_bytes(head_test)
    manifest_path = repo / "pm_acceptance/errata/task-a.json"
    manifest_path.parent.mkdir(parents=True)
    manifest = _erratum_bytes(
        task=task,
        base_test=base_test,
        head_test=head_test,
        failed=("pm_acceptance/tasks/task-a/test_contract.py::test_contract",),
        passed=("pm_acceptance/tasks/task-a/test_contract.py::test_compatibility",),
        historical_active_task_commit_sha=historical_active,
    )
    if manifest_transform is not None:
        manifest = manifest_transform(manifest)
    manifest_path.write_bytes(manifest)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "frozen erratum")
    head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head, task, base_test, head_test


def _erratum_errors(repo: Path, base: str, head: str, task: ActiveTask) -> tuple[str, ...]:
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        return frozen_erratum_transition_errors(
            base,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            changed_paths_from_git(base, head),
        )
    finally:
        os.chdir(old_cwd)


def _build_frozen_erratum_v2_repo(
    tmp_path: Path,
    *,
    head_test: bytes | None = None,
    manifest_transform=None,
) -> tuple[Path, str, str, str, ActiveTask, bytes, bytes, bytes]:
    repo = tmp_path / "erratum-v2-repo"
    test_path = repo / "pm_acceptance/tasks/task-a/test_contract.py"
    contract_path = repo / "docs/frozen_contracts/tasks/task-a.md"
    active_path = repo / "pm_acceptance/active_task.json"
    test_path.parent.mkdir(parents=True)
    contract_path.parent.mkdir(parents=True)
    original_test = (
        b'FIXTURE = b"invalid-v0"\n\n'
        b"def helper():\n    return FIXTURE\n\n"
        b"def test_contract():\n    assert helper()\n\n"
        b"def test_compatibility():\n    assert True\n"
    )
    first_test = original_test.replace(b'FIXTURE = b"invalid-v0"', b'FIXTURE = b"invalid-v1"')
    if head_test is None:
        head_test = first_test.replace(b'FIXTURE = b"invalid-v1"', b'FIXTURE = b"valid-v2"')
    test_path.write_bytes(original_test)
    contract_path.write_text("# Frozen task\n")
    active_path.parent.mkdir(parents=True, exist_ok=True)
    task = _active_task()
    active_path.write_bytes(_task_bytes(task))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "historical active task")
    historical_active = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "cancel invalid original")

    active_path.write_bytes(_task_bytes(task))
    test_path.write_bytes(first_test)
    predecessor_path = repo / "pm_acceptance/errata/task-a.json"
    predecessor_path.parent.mkdir(parents=True)
    predecessor_manifest = _erratum_bytes(
        task=task,
        base_test=original_test,
        head_test=first_test,
        failed=("pm_acceptance/tasks/task-a/test_contract.py::test_contract",),
        passed=("pm_acceptance/tasks/task-a/test_contract.py::test_compatibility",),
        historical_active_task_commit_sha=historical_active,
    )
    predecessor_path.write_bytes(predecessor_manifest)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "first frozen erratum")
    predecessor_commit = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(CANONICAL)
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "cancel invalid first erratum")
    base = _git(repo, "rev-parse", "HEAD")

    active_path.write_bytes(_task_bytes(task))
    test_path.write_bytes(head_test)
    manifest_path = repo / "pm_acceptance/errata/task-a.v2.json"
    manifest = _erratum_v2_bytes(
        task=task,
        base_test=first_test,
        head_test=head_test,
        predecessor_manifest=predecessor_manifest,
        predecessor_commit_sha=predecessor_commit,
        failed=("pm_acceptance/tasks/task-a/test_contract.py::test_contract",),
        passed=("pm_acceptance/tasks/task-a/test_contract.py::test_compatibility",),
        historical_active_task_commit_sha=historical_active,
    )
    if manifest_transform is not None:
        manifest = manifest_transform(manifest)
    manifest_path.write_bytes(manifest)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "second frozen erratum")
    head = _git(repo, "rev-parse", "HEAD")
    return (
        repo,
        predecessor_commit,
        base,
        head,
        task,
        predecessor_manifest,
        first_test,
        head_test,
    )


def _erratum_v2_errors(repo: Path, base: str, head: str, task: ActiveTask) -> tuple[str, ...]:
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        return frozen_erratum_v2_transition_errors(
            base,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            changed_paths_from_git(base, head),
        )
    finally:
        os.chdir(old_cwd)


def test_frozen_erratum_accepts_exact_reactivation_and_helper_only_fix(tmp_path: Path):
    repo, base, head, task, _base_test, _head_test = _build_frozen_erratum_repo(tmp_path)
    assert _erratum_errors(repo, base, head, task) == ()


def test_frozen_erratum_rejects_historical_active_task_byte_mismatch(tmp_path: Path):
    repo, base, _head, task, _base_test, _head_test = _build_frozen_erratum_repo(tmp_path)
    manifest_path = repo / "pm_acceptance/errata/task-a.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["historical_active_task_commit_sha"] = base
    manifest_path.write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    _git(repo, "add", str(manifest_path.relative_to(repo)))
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    head = _git(repo, "rev-parse", "HEAD")
    assert "historical_active_task_bytes_mismatch" in _erratum_errors(
        repo,
        base,
        head,
        task,
    )


def test_frozen_erratum_requires_inactive_base_and_exact_three_paths(tmp_path: Path):
    repo, base, head, task, _base_test, _head_test = _build_frozen_erratum_repo(tmp_path)
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        changed = changed_paths_from_git(base, head)
        assert frozen_erratum_transition_errors(base, head, task, task, changed) == (
            "erratum_base_task_not_inactive:task-a",
        )
        errors = frozen_erratum_transition_errors(
            base,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            changed[:-1],
        )
    finally:
        os.chdir(old_cwd)
    assert "frozen_erratum_changed_path_count:2" in errors
    assert "erratum_test_path_scope_mismatch" in errors


def test_frozen_erratum_rejects_changed_test_function_ast(tmp_path: Path):
    head_test = (
        b'FIXTURE = b"valid"\n\n'
        b"def helper():\n    return FIXTURE\n\n"
        b"def test_contract():\n    assert helper() == b'other'\n\n"
        b"def test_compatibility():\n    assert True\n"
    )
    repo, base, head, task, _base_test, _ = _build_frozen_erratum_repo(
        tmp_path,
        head_test=head_test,
    )
    assert "frozen_test_function_ast_changed" in _erratum_errors(repo, base, head, task)


def test_frozen_erratum_allows_legacy_broad_raise_in_immutable_test_ast(
    tmp_path: Path,
):
    base_test = (
        b"import pytest\n\n"
        b'FIXTURE = b"invalid"\n\n'
        b"def helper():\n    return FIXTURE\n\n"
        b"def test_contract():\n"
        b"    with pytest.raises(Exception):\n"
        b"        raise ValueError\n\n"
        b"def test_compatibility():\n    assert True\n"
    )
    head_test = base_test.replace(b'FIXTURE = b"invalid"', b'FIXTURE = b"valid"')
    repo, base, head, task, _base_test, _head_test = _build_frozen_erratum_repo(
        tmp_path,
        base_test=base_test,
        head_test=head_test,
    )
    assert _erratum_errors(repo, base, head, task) == ()


def test_frozen_erratum_still_rejects_new_broad_raise_in_mutable_helper(
    tmp_path: Path,
):
    base_test = (
        b"import pytest\n\n"
        b'FIXTURE = b"invalid"\n\n'
        b"def helper():\n    return FIXTURE\n\n"
        b"def test_contract():\n"
        b"    with pytest.raises(Exception):\n"
        b"        raise ValueError\n\n"
        b"def test_compatibility():\n    assert True\n"
    )
    head_test = base_test.replace(b'FIXTURE = b"invalid"', b'FIXTURE = b"valid"') + (
        b"\ndef helper_unsafe():\n"
        b"    with pytest.raises(Exception):\n"
        b"        pass\n"
    )
    repo, base, head, task, _base_test, _head_test = _build_frozen_erratum_repo(
        tmp_path,
        base_test=base_test,
        head_test=head_test,
    )
    assert "unsafe_frozen_test_pattern:broad_pytest_raises" in _erratum_errors(
        repo,
        base,
        head,
        task,
    )


@pytest.mark.parametrize(
    ("unsafe_source", "expected"),
    (
        (b"\npytestmark = pytest.mark.xfail\n", "unsafe_frozen_test_pattern:skip_or_xfail"),
        (
            b"\ndef helper_unsafe():\n    with pytest.raises(Exception):\n        pass\n",
            "unsafe_frozen_test_pattern:broad_pytest_raises",
        ),
        (
            b"\ndef helper_unsafe():\n    try:\n        pass\n    except BaseException:\n        pass\n",
            "unsafe_frozen_test_pattern:broad_exception_handler",
        ),
    ),
)
def test_frozen_erratum_rejects_skip_xfail_and_broad_exception_patterns(
    tmp_path: Path,
    unsafe_source: bytes,
    expected: str,
):
    base = (
        b"import pytest\n\n"
        b'FIXTURE = b"invalid"\n\n'
        b"def helper():\n    return FIXTURE\n\n"
        b"def test_contract():\n    assert helper()\n\n"
        b"def test_compatibility():\n    assert True\n"
    )
    head_test = base.replace(b'FIXTURE = b"invalid"', b'FIXTURE = b"valid"') + unsafe_source
    repo, base_sha, head, task, _base_test, _ = _build_frozen_erratum_repo(
        tmp_path,
        head_test=head_test,
    )
    assert expected in _erratum_errors(repo, base_sha, head, task)


def test_frozen_erratum_rejects_hash_and_red_node_manifest_lies(tmp_path: Path):
    def transform(raw: bytes) -> bytes:
        obj = json.loads(raw)
        obj["base_sha256"] = "0" * 64
        obj["expected_red_failed_node_ids"] = [
            "pm_acceptance/tasks/task-a/test_contract.py::test_not_present"
        ]
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"

    repo, base, head, task, _base_test, _head_test = _build_frozen_erratum_repo(
        tmp_path,
        manifest_transform=transform,
    )
    errors = _erratum_errors(repo, base, head, task)
    assert "base_erratum_test_sha256_mismatch" in errors
    assert "missing_erratum_red_test:test_contract" in errors
    assert "unknown_erratum_red_test:test_not_present" in errors


def test_frozen_erratum_cli_emits_reactivated_head_task_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    repo, base, head, _task, _base_test, _head_test = _build_frozen_erratum_repo(tmp_path)
    _git(repo, "checkout", "-q", base)
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        status = check_task_scope_main([
            "--task-file", "pm_acceptance/active_task.json",
            "--base-sha", base,
            "--head-sha", head,
            "--actor", "brullik",
            "--labels-json", '["pm-frozen-erratum"]',
        ])
        payload = json.loads(capsys.readouterr().out)
    finally:
        os.chdir(old_cwd)
    assert status == 0, payload
    assert payload == {
        "changed_count": 3,
        "errors": [],
        "mode": "pm-frozen-erratum",
        "ok": True,
        "task_id": "task-a",
    }


def test_frozen_erratum_v2_accepts_exact_three_path_audit_chain(tmp_path: Path):
    repo, predecessor, base, head, task, predecessor_manifest, first_test, _head_test = (
        _build_frozen_erratum_v2_repo(tmp_path)
    )
    assert _erratum_v2_errors(repo, base, head, task) == ()
    manifest = parse_frozen_erratum_v2_manifest_bytes(
        (repo / "pm_acceptance/errata/task-a.v2.json").read_bytes()
    )
    assert manifest.predecessor_commit_sha == predecessor
    assert manifest.predecessor_manifest_sha256 == hashlib.sha256(predecessor_manifest).hexdigest()
    assert manifest.base_sha256 == hashlib.sha256(first_test).hexdigest()


def test_frozen_erratum_v2_rejects_predecessor_hash_and_test_chain_lies(tmp_path: Path):
    def transform(raw: bytes) -> bytes:
        obj = json.loads(raw)
        obj["predecessor_manifest_sha256"] = "0" * 64
        obj["base_sha256"] = "1" * 64
        obj["issue_number"] = 99
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"

    repo, _predecessor, base, head, task, _manifest, _first, _second = (
        _build_frozen_erratum_v2_repo(tmp_path, manifest_transform=transform)
    )
    errors = _erratum_v2_errors(repo, base, head, task)
    assert "erratum_v2_predecessor_manifest_sha256_mismatch" in errors
    assert "erratum_v2_predecessor_test_sha256_mismatch" in errors
    assert "erratum_v2_predecessor_issue_number_mismatch" in errors
    assert "base_erratum_v2_test_sha256_mismatch" in errors


def test_frozen_erratum_v2_rejects_wrong_predecessor_commit_state(tmp_path: Path):
    captured_base = ""

    def build_transform(raw: bytes) -> bytes:
        obj = json.loads(raw)
        obj["predecessor_commit_sha"] = captured_base
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode() + b"\n"

    repo, _predecessor, base, _head, task, predecessor_manifest, first_test, second_test = (
        _build_frozen_erratum_v2_repo(tmp_path)
    )
    captured_base = base
    manifest_path = repo / "pm_acceptance/errata/task-a.v2.json"
    manifest_path.write_bytes(
        build_transform(
            _erratum_v2_bytes(
                task=task,
                base_test=first_test,
                head_test=second_test,
                predecessor_manifest=predecessor_manifest,
                predecessor_commit_sha="2" * 40,
                failed=("pm_acceptance/tasks/task-a/test_contract.py::test_contract",),
                passed=("pm_acceptance/tasks/task-a/test_contract.py::test_compatibility",),
                historical_active_task_commit_sha=json.loads(predecessor_manifest)[
                    "historical_active_task_commit_sha"
                ],
            )
        )
    )
    _git(repo, "add", "pm_acceptance/errata/task-a.v2.json")
    _git(repo, "commit", "-q", "--amend", "--no-edit")
    head = _git(repo, "rev-parse", "HEAD")
    errors = _erratum_v2_errors(repo, base, head, task)
    assert "erratum_v2_predecessor_active_task_bytes_mismatch" in errors


def test_frozen_erratum_v2_is_one_time_and_requires_v1_and_exact_scope(tmp_path: Path):
    repo, predecessor, base, head, task, _manifest, _first, _second = (
        _build_frozen_erratum_v2_repo(tmp_path)
    )
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        actual = changed_paths_from_git(base, head)
        scope_errors = frozen_erratum_v2_transition_errors(
            base,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            actual[:-1],
        )
        reused_errors = frozen_erratum_v2_transition_errors(
            head,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            (
                "pm_acceptance/active_task.json",
                "pm_acceptance/errata/task-a.v2.json",
                "pm_acceptance/tasks/task-a/test_contract.py",
            ),
        )
        before_v1 = _git(repo, "rev-parse", f"{predecessor}^")
        missing_v1_errors = frozen_erratum_v2_transition_errors(
            before_v1,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            (
                "pm_acceptance/active_task.json",
                "pm_acceptance/errata/task-a.v2.json",
                "pm_acceptance/tasks/task-a/test_contract.py",
            ),
        )
        unsupported_v3_errors = frozen_erratum_v2_transition_errors(
            base,
            head,
            parse_active_task_bytes(CANONICAL),
            task,
            (
                "pm_acceptance/active_task.json",
                "pm_acceptance/errata/task-a.v3.json",
                "pm_acceptance/tasks/task-a/test_contract.py",
            ),
        )
    finally:
        os.chdir(old_cwd)
    assert "frozen_erratum_v2_changed_path_count:2" in scope_errors
    assert "erratum_v2_test_path_scope_mismatch" in scope_errors
    assert "erratum_v2_manifest_already_exists:pm_acceptance/errata/task-a.v2.json" in reused_errors
    assert "erratum_v2_predecessor_manifest_missing:pm_acceptance/errata/task-a.json" in missing_v1_errors
    assert "erratum_v2_manifest_path_missing:pm_acceptance/errata/task-a.v2.json" in unsupported_v3_errors
    assert "pm_frozen_erratum_v2_out_of_scope:pm_acceptance/errata/task-a.v3.json" in unsupported_v3_errors


def test_frozen_erratum_v2_rejects_test_function_ast_change(tmp_path: Path):
    head_test = (
        b'FIXTURE = b"valid-v2"\n\n'
        b"def helper():\n    return FIXTURE\n\n"
        b"def test_contract():\n    assert helper() == b'changed'\n\n"
        b"def test_compatibility():\n    assert True\n"
    )
    repo, _predecessor, base, head, task, _manifest, _first, _second = (
        _build_frozen_erratum_v2_repo(tmp_path, head_test=head_test)
    )
    assert "frozen_test_function_ast_changed" in _erratum_v2_errors(
        repo,
        base,
        head,
        task,
    )


def test_frozen_erratum_v2_cli_dispatches_by_v2_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    repo, _predecessor, base, head, _task, _manifest, _first, _second = (
        _build_frozen_erratum_v2_repo(tmp_path)
    )
    _git(repo, "checkout", "-q", base)
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        status = check_task_scope_main([
            "--task-file", "pm_acceptance/active_task.json",
            "--base-sha", base,
            "--head-sha", head,
            "--actor", "brullik",
            "--labels-json", '["pm-frozen-erratum"]',
        ])
        payload = json.loads(capsys.readouterr().out)
    finally:
        os.chdir(old_cwd)
    assert status == 0, payload
    assert payload["changed_count"] == 3
    assert payload["mode"] == "pm-frozen-erratum"
    assert payload["task_id"] == "task-a"
    assert payload["errors"] == []


def test_cli_reads_and_validates_head_active_task_via_git_show(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    repo = tmp_path / "repo"
    task_file = repo / "pm_acceptance/active_task.json"
    task_file.parent.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    task_file.write_bytes(CANONICAL)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "task")
    task_test = repo / "pm_acceptance/tasks/task-a/test_contract.py"
    task_test.parent.mkdir(parents=True)
    task_test.write_text("def test_contract():\n    assert False\n")
    active = _active_task()
    noncanonical = json.dumps(json.loads(_task_bytes(active)), indent=2).encode() + b"\n"
    task_file.write_bytes(noncanonical)
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "noncanonical head")
    bad_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        bad_status = check_task_scope_main([
            "--task-file", "pm_acceptance/active_task.json",
            "--base-sha", base,
            "--head-sha", bad_head,
            "--actor", "brullik",
            "--labels-json", '["pm-task-definition"]',
        ])
        bad_payload = json.loads(capsys.readouterr().out)
    finally:
        os.chdir(old_cwd)
    assert bad_status == 1
    assert bad_payload["errors"] == ["noncanonical_task_bytes"]

    _git(repo, "checkout", "-q", "task")
    task_file.write_bytes(_task_bytes(active))
    _git(repo, "add", "pm_acceptance/active_task.json")
    _git(repo, "commit", "-q", "-m", "canonical head")
    good_head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        good_status = check_task_scope_main([
            "--task-file", "pm_acceptance/active_task.json",
            "--base-sha", base,
            "--head-sha", good_head,
            "--actor", "brullik",
            "--labels-json", '["pm-task-definition"]',
        ])
        good_payload = json.loads(capsys.readouterr().out)
    finally:
        os.chdir(old_cwd)
    assert good_status == 0
    assert good_payload["ok"] is True
    assert good_payload["task_id"] == "task-a"


def test_deleted_changed_task_test_is_not_accepted_as_head_evidence(tmp_path: Path):
    repo = tmp_path / "repo"
    task_dir = repo / "pm_acceptance/tasks/task-a"
    task_dir.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    test_path = task_dir / "test_contract.py"
    test_path.write_text("def test_contract():\n    assert False\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "task")
    test_path.unlink()
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "delete")
    head = _git(repo, "rev-parse", "HEAD")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        errors = task_definition_head_path_errors(
            head,
            _active_task(),
            ("pm_acceptance/tasks/task-a/test_contract.py",),
        )
    finally:
        os.chdir(old_cwd)
    assert errors == (
        "head_task_path_missing:pm_acceptance/tasks/task-a/test_contract.py",
    )


def test_non_utf8_head_task_file_is_rejected(tmp_path: Path):
    repo = tmp_path / "repo"
    task_dir = repo / "pm_acceptance/tasks/task-a"
    task_dir.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    test_path = task_dir / "test_contract.py"
    test_path.write_bytes(b"# coding: latin-1\nvalue = '\xff'\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "non utf8")
    head = _git(repo, "rev-parse", "HEAD")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        errors = task_definition_head_path_errors(
            head,
            _active_task(),
            ("pm_acceptance/tasks/task-a/test_contract.py",),
        )
    finally:
        os.chdir(old_cwd)
    assert errors == (
        "head_task_path_not_utf8:pm_acceptance/tasks/task-a/test_contract.py",
    )


def test_open_transition_rejects_reused_frozen_task_id(tmp_path: Path):
    repo = tmp_path / "repo"
    old_task = repo / "pm_acceptance/tasks/task-a/test_old.py"
    old_task.parent.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    old_task.write_text("def test_old():\n    assert True\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "old frozen task")
    base = _git(repo, "rev-parse", "HEAD")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        errors = task_definition_base_path_errors(
            base,
            parse_active_task_bytes(CANONICAL),
            _active_task(),
        )
    finally:
        os.chdir(old_cwd)
    assert errors == ("task_id_reused:task-a",)


def test_multi_commit_diff_and_rename_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "AGENTS.md").write_text("rules\n")
    (repo / "plain.txt").write_text("plain\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "head")
    (repo / "a.txt").write_text("a\n")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "one")
    (repo / "b.txt").write_text("b\n")
    _git(repo, "add", "b.txt")
    _git(repo, "commit", "-q", "-m", "two")
    head = _git(repo, "rev-parse", "HEAD")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        assert changed_paths_from_git(base, head) == ("a.txt", "b.txt")
        _git(repo, "mv", "AGENTS.md", "moved.txt")
        _git(repo, "mv", "plain.txt", "pm_acceptance_file.txt")
        _git(repo, "commit", "-q", "-m", "renames")
        renamed = changed_paths_from_git(head, _git(repo, "rev-parse", "HEAD"))
    finally:
        os.chdir(old_cwd)
    assert renamed == ("AGENTS.md", "moved.txt", "plain.txt", "pm_acceptance_file.txt")
    assert "protected_path_changed:AGENTS.md" in protected_path_errors(renamed)


def test_protected_deletion_is_reported_by_raw_diff(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "pm@example.test")
    _git(repo, "config", "user.name", "PM")
    (repo / "AGENTS.md").write_text("rules\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    (repo / "AGENTS.md").unlink()
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-q", "-m", "delete")
    old_cwd = Path.cwd()
    try:
        os.chdir(repo)
        changed = changed_paths_from_git(base, _git(repo, "rev-parse", "HEAD"))
    finally:
        os.chdir(old_cwd)
    assert changed == ("AGENTS.md",)
    assert protected_path_errors(changed) == ("protected_path_changed:AGENTS.md",)


def test_isolated_acceptance_ignores_malicious_root_conftest(tmp_path: Path):
    head = tmp_path / "head"
    acc = tmp_path / "pm_acceptance"
    head.mkdir()
    acc.mkdir()
    (head / "conftest.py").write_text("import pytest\ndef pytest_collection_modifyitems(items):\n    pytest.skip('malicious skip')\n")
    (acc / "test_acceptance.py").write_text("def test_acceptance_runs():\n    assert True\n")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(acc), "-q", f"--confcutdir={acc}", "-c", os.devnull],
        cwd=head,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0
    assert "1 passed" in result.stdout
    assert "malicious skip" not in result.stdout + result.stderr


def _stage_isolated_tree(temp: Path) -> None:
    scripts = temp / "scripts"
    pm = temp / "pm_acceptance"
    workflows = temp / ".github/workflows"
    scripts.mkdir(parents=True)
    pm.mkdir()
    workflows.mkdir(parents=True)
    (scripts / "__init__.py").write_text("")
    repo_root = Path(__file__).resolve().parents[1]
    (scripts / "check_protected_paths.py").write_text((repo_root / "scripts/check_protected_paths.py").read_text())
    (scripts / "check_task_scope.py").write_text((repo_root / "scripts/check_task_scope.py").read_text())
    (workflows / "pm-acceptance.yml").write_text(
        (repo_root / ".github/workflows/pm-acceptance.yml").read_text()
    )
    (temp / "pytest.ini").write_text("[pytest]\n")


def test_exact_base_harness_temp_import_shape_runs_one_test(tmp_path: Path):
    temp = tmp_path / "temp"
    temp.mkdir()
    _stage_isolated_tree(temp)
    (temp / "pm_acceptance/test_acceptance.py").write_text(
        "from scripts.check_protected_paths import protected_path_errors\n"
        "from scripts.check_task_scope import parse_active_task_bytes\n"
        "def test_acceptance_imports():\n"
        "    assert protected_path_errors(('src/x.py',)) == ()\n"
        "    assert parse_active_task_bytes.__name__ == 'parse_active_task_bytes'\n"
    )
    env = dict(os.environ, PYTHONPATH=str(temp), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "pm_acceptance", "-q", "-c", str(temp / "pytest.ini"), f"--confcutdir={temp / 'pm_acceptance'}"],
        cwd=temp, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert result.returncode == 0
    assert "1 passed" in result.stdout


def test_head_task_definition_collection_valid_and_syntax_error(tmp_path: Path):
    good = tmp_path / "good"
    good.mkdir()
    _stage_isolated_tree(good)
    good_task = good / "pm_acceptance/tasks/task-a"
    good_task.mkdir(parents=True)
    (good_task / "test_acceptance.py").write_text("def test_collectable():\n    assert False\n")
    env = dict(os.environ, PYTHONPATH=str(good), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    compile_good = subprocess.run([sys.executable, "-m", "compileall", "-q", str(good_task)], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    collect_good = subprocess.run(
        [sys.executable, "-m", "pytest", str(good_task), "--collect-only", "-q", "-c", str(good / "pytest.ini"), f"--confcutdir={good_task}"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    assert compile_good.returncode == 0
    assert collect_good.returncode == 0
    assert "test_acceptance.py::test_collectable" in collect_good.stdout
    assert "failed" not in collect_good.stdout.lower()

    bad = tmp_path / "bad"
    bad.mkdir()
    _stage_isolated_tree(bad)
    bad_task = bad / "pm_acceptance/tasks/task-a"
    bad_task.mkdir(parents=True)
    (bad_task / "test_acceptance.py").write_text("def broken(:\n")
    env_bad = dict(os.environ, PYTHONPATH=str(bad), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    compile_bad = subprocess.run([sys.executable, "-m", "compileall", "-q", str(bad_task)], env=env_bad, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert compile_bad.returncode != 0
