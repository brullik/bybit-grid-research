from __future__ import annotations

import ast
import re
from pathlib import Path
import tomllib

import bybit_grid


TASK_ID = "documentation-current-architecture-status-runbooks"
SENTINEL = "current_documentation_unavailable"
MARKER = "<!-- documentation-contract: current-v1 -->"
HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
REQUIRED_DOC_PATHS = (
    ".env.example",
    "00_PROJECT_CONTEXT_FOR_CODEX.md",
    "01_PROJECT_RULES.md",
    "02_TECHNICAL_SPEC.md",
    "03_SPRINT_01_API_DATA_FEASIBILITY.md",
    "04_CODEX_PROMPT_SPRINT_01.md",
    "05_RISK_AND_RESEARCH_POLICY.md",
    "PROJECT_BOARD.md",
    "README.md",
    "docs/CURRENT_ARCHITECTURE_AND_STATUS.md",
    "docs/EVIDENCE_MAP.md",
    "docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md",
    "docs/SETUP_TEST_RUNBOOK.md",
)
MINIMUM_VISIBLE_CHARACTERS = {
    ".env.example": 300,
    "00_PROJECT_CONTEXT_FOR_CODEX.md": 600,
    "01_PROJECT_RULES.md": 900,
    "02_TECHNICAL_SPEC.md": 900,
    "03_SPRINT_01_API_DATA_FEASIBILITY.md": 400,
    "04_CODEX_PROMPT_SPRINT_01.md": 400,
    "05_RISK_AND_RESEARCH_POLICY.md": 900,
    "PROJECT_BOARD.md": 500,
    "README.md": 1_000,
    "docs/CURRENT_ARCHITECTURE_AND_STATUS.md": 1_200,
    "docs/EVIDENCE_MAP.md": 1_200,
    "docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md": 1_200,
    "docs/SETUP_TEST_RUNBOOK.md": 1_200,
}
RISK_PAIRS = {
    "capital_usdt": "500",
    "max_loss_per_grid_usdt": "5",
    "max_grids_per_instrument": "1",
    "initial_global_concurrency_cap": "1",
    "grid_mode": "neutral",
    "grid_type": "geometric",
    "exit_policy": "SL-only",
    "take_profit_enabled": "false",
    "trailing_enabled": "false",
    "withdrawals_authorized": "false",
    "first_live_requires_manual_telegram_confirmation": "true",
}
EXPECTED_ENV_VALUES = {
    "ALLOW_LIVE_TRADING": "NO",
    "BYBIT_API_BASE_URL": "https://api.bybit.com",
    "BYBIT_API_KEY": "",
    "BYBIT_API_SECRET": "",
    "BYBIT_ENV": "mainnet",
    "BYBIT_FGRID_GRID_MODE_NEUTRAL": "1",
    "BYBIT_FGRID_GRID_TYPE_GEOMETRIC": "2",
    "BYBIT_FGRID_VALIDATE_PATH": "/v5/fgridbot/validate",
    "BYBIT_RECV_WINDOW": "5000",
    "DATA_DIR": "./data",
    "GRID_VALIDATE_ENABLED": "false",
    "LIVE_TRADING_ENABLED": "false",
    "LOG_LEVEL": "INFO",
}
MACHINE_PAIR = re.compile(r"`([a-z][a-z0-9_]*)`:\s*`([^`]+)`")
ROOT = Path(bybit_grid.__file__).resolve().parents[2]


def _read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", "strict")


def _docs() -> dict[str, str]:
    try:
        docs = {path: _read_text(ROOT / path) for path in REQUIRED_DOC_PATHS}
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(SENTINEL) from exc
    if not docs["README.md"].startswith(MARKER):
        raise RuntimeError(SENTINEL)
    visible_docs: dict[str, str] = {}
    for path, text in docs.items():
        visible = HTML_COMMENT.sub("", text) if path.endswith(".md") else text
        if len(visible) < MINIMUM_VISIBLE_CHARACTERS[path]:
            raise RuntimeError(SENTINEL)
        if path.endswith(".md"):
            nonblank = [line for line in visible.splitlines() if line.strip()]
            if (
                not nonblank
                or not nonblank[0].startswith("# ")
                or not any(line.startswith("## ") for line in nonblank[1:])
            ):
                raise RuntimeError(SENTINEL)
        visible_docs[path] = visible
    return visible_docs


def _combined(docs: dict[str, str]) -> str:
    return "\n".join(docs.values())


def _env_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert "=" in line
        key, value = line.split("=", 1)
        assert key and key not in values
        values[key] = value
    return values


def _require_exact_pairs(text: str, expected: dict[str, str]) -> None:
    observed: dict[str, set[str]] = {}
    for name, value in MACHINE_PAIR.findall(text):
        observed.setdefault(name, set()).add(value)
    for name, value in expected.items():
        assert observed.get(name) == {value}, (name, observed.get(name))


def _assert_no_positive_claims(text: str, subjects: tuple[str, ...]) -> None:
    positives = (
        "allowed",
        "authorized",
        "available",
        "enabled",
        "fully implemented",
        "разрешен",
        "разрешён",
        "реализован",
        "доступен",
        "включен",
        "включён",
    )
    negatives = (
        "false",
        "forbidden",
        "not ",
        "no ",
        "unavailable",
        "disabled",
        "запрещ",
        "не ",
        "недоступ",
        "отключ",
    )
    for raw_line in text.casefold().splitlines():
        if re.search(r"`[a-z][a-z0-9_]*`:\s*`false`", raw_line):
            continue
        for subject in subjects:
            subject_index = raw_line.find(subject)
            if subject_index < 0:
                continue
            for positive in positives:
                positive_index = raw_line.find(positive, subject_index + len(subject))
                if positive_index < 0:
                    continue
                prefix = raw_line[:positive_index]
                assert any(negative in prefix for negative in negatives), raw_line


def _settings_fields() -> tuple[str, ...]:
    tree = ast.parse(_read_text(ROOT / "src/bybit_grid/config.py"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return tuple(
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign)
                and isinstance(statement.target, ast.Name)
                and not statement.target.id.startswith("_")
            )
    raise AssertionError("Settings class missing")


def _risk_texts(docs: dict[str, str]) -> tuple[str, ...]:
    return (
        docs["README.md"],
        docs["01_PROJECT_RULES.md"],
        docs["05_RISK_AND_RESEARCH_POLICY.md"],
        docs["docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md"],
    )


def test_readme_is_current_entrypoint_and_not_bootstrap() -> None:
    docs = _docs()
    readme = docs["README.md"]
    assert readme.lstrip().startswith("# Bybit Grid Research")
    assert "не готовый торговый бот" in readme
    assert "fail-closed validate-only" in readme
    _require_exact_pairs(
        readme,
        {
            "live_execution_implemented": "false",
            "telegram_runtime_implemented": "false",
            "vps_deployment_implemented": "false",
        },
    )
    forbidden = (
        "Стартовый пакет проекта",
        "Текущая стадия: **Sprint 01",
        "Создай пустой GitHub-репозиторий",
        "Скопируй туда эти файлы",
    )
    assert all(item not in readme for item in forbidden)


def test_readme_links_every_current_document() -> None:
    docs = _docs()
    readme = docs["README.md"]
    expected = set(REQUIRED_DOC_PATHS) - {"README.md", ".env.example"}
    targets = {
        target.split("#", 1)[0]
        for _label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", readme)
        if not target.startswith(("http://", "https://", "#"))
    }
    assert expected <= targets
    assert ".env.example" in readme


def test_current_status_matches_completed_and_open_work() -> None:
    docs = _docs()
    status = docs["docs/CURRENT_ARCHITECTURE_AND_STATUS.md"]
    context = docs["00_PROJECT_CONTEXT_FOR_CODEX.md"]
    assert "35a3b9c05b1bf3d86756e449b2735bef0893bc45" in status
    assert "PR #143" in status
    assert all(f"#{number}" in status for number in (129, 131, 133, 134))
    assert "#130" not in status or any(
        marker in _combined(docs).lower() for marker in ("закры", "closed")
    )
    assert "NO_ACTIVE_IMPLEMENTATION" in _combined(docs)
    for required in (
        "AGENTS.md",
        "pm_acceptance/active_task.json",
        "NO_ACTIVE_IMPLEMENTATION",
        "production-edit authority",
        "docs/CURRENT_ARCHITECTURE_AND_STATUS.md",
    ):
        assert required in context


def test_architecture_component_paths_exist() -> None:
    docs = _docs()
    architecture = docs["docs/CURRENT_ARCHITECTURE_AND_STATUS.md"]
    specification = docs["02_TECHNICAL_SPEC.md"]
    paths = (
        "src/bybit_grid/bybit/validate_only.py",
        "src/bybit_grid/bybit/client.py",
        "src/bybit_grid/data/public_batch/historical_plan.py",
        "src/bybit_grid/data/public_batch/historical_response.py",
        "src/bybit_grid/data/public_batch/historical_transcript.py",
        "src/bybit_grid/data/public_batch/historical_evidence.py",
        "src/bybit_grid/data/market_store/reader.py",
        "scripts/build_range_candidates.py",
        "scripts/build_candidate_outcomes.py",
        "src/bybit_grid/backtest/neutral_grid/engine.py",
        "src/bybit_grid/backtest/ohlc_replay/replay.py",
        "src/bybit_grid/research/scoring/components.py",
        "src/bybit_grid/research/walk_forward/splits.py",
        "src/bybit_grid/backtest/grid_simulator.py",
    )
    assert all((ROOT / path).is_file() for path in paths)
    assert all(
        Path(path).name in architecture or path in architecture for path in paths[:6]
    )
    specification_paths = (
        "src/bybit_grid/data/market_store",
        "src/bybit_grid/data/public_batch/historical_*.py",
        "scripts/build_range_candidates.py",
        "scripts/build_candidate_outcomes.py",
        "src/bybit_grid/backtest/neutral_grid",
        "src/bybit_grid/backtest/ohlc_replay",
        "src/bybit_grid/research/scoring",
        "src/bybit_grid/research/walk_forward",
        "src/bybit_grid/backtest/grid_simulator.py",
    )
    assert all(path in specification for path in specification_paths)
    assert "Missing vertical path" in specification
    assert "legacy data/raw" in specification
    assert "не доказаны" in specification


def test_architecture_separates_legacy_and_strict_data_paths() -> None:
    docs = _docs()
    architecture = docs["docs/CURRENT_ARCHITECTURE_AND_STATUS.md"]
    assert "Strict versus legacy data paths" in architecture
    assert "data/raw/klines" in architecture
    assert "data/raw/mark_klines" in architecture
    assert "data/raw/funding" in architecture
    assert "silent fallback" in architecture.lower()
    range_source = _read_text(ROOT / "scripts/build_range_candidates.py")
    assert 'default="data"' in range_source
    assert '/ "raw" / "klines"' in range_source
    assert "data/raw" in _read_text(ROOT / "scripts/build_candidate_outcomes.py")


def test_architecture_records_every_missing_end_to_end_link() -> None:
    docs = _docs()
    text = docs["docs/CURRENT_ARCHITECTURE_AND_STATUS.md"].lower()
    required = (
        "downloader",
        "canonical-store reader",
        "semantic replay",
        "native quantity",
        "liquidation",
        "risk",
        "proxy-only",
        "walk-forward",
        "portfolio",
        "telegram",
        "deployment",
    )
    assert all(item in text for item in required)


def test_backtest_and_parameter_selection_are_not_overclaimed() -> None:
    docs = _docs()
    text = _combined(docs).lower()
    assert "grid_simulator.py" in text and "placeholder" in text
    assert "proxy-only" in text
    assert "parameter selection" in text
    assert "не доказ" in text or "unproven" in text
    assert "risk_budget_proven_bool" in _read_text(
        ROOT / "src/bybit_grid/research/scoring/components.py"
    )
    assert "sufficient_for_parameter_selection_bool" in _read_text(
        ROOT / "src/bybit_grid/research/walk_forward/splits.py"
    )
    assert "Placeholder" in _read_text(
        ROOT / "src/bybit_grid/backtest/grid_simulator.py"
    )


def test_project_board_matches_repository_truth() -> None:
    docs = _docs()
    board = docs["PROJECT_BOARD.md"]
    assert all(f"#{number}" in board for number in (129, 131, 132, 133, 134))
    assert "#143" in board
    assert "NO_ACTIVE_IMPLEMENTATION" in board
    assert "06.4G" in board and any(
        marker in board.lower() for marker in ("заблок", "blocked")
    )
    assert "Now\n\nSprint 06.4A" not in board
    assert "active_task.json" in board


def test_bootstrap_sprint_documents_are_archived_and_non_executable() -> None:
    docs = _docs()
    for path in (
        "03_SPRINT_01_API_DATA_FEASIBILITY.md",
        "04_CODEX_PROMPT_SPRINT_01.md",
    ):
        text = docs[path]
        assert text.startswith("# Historical Archive")
        assert "не " in text.lower()
        assert "current" in text.lower() or "актуаль" in text.lower()
        assert "authority" in text.lower() or "полномоч" in text.lower()


def test_binding_risk_policy_is_exact_and_consistent() -> None:
    docs = _docs()
    texts = _risk_texts(docs)
    combined = "\n".join(texts).lower()
    for text in texts:
        _require_exact_pairs(text, RISK_PAIRS)
        _assert_no_positive_claims(
            text,
            ("tp", "take profit", "trailing", "withdrawal"),
        )
    assert (
        "одна сетка на инструмент" in combined
        or "max_grids_per_instrument | 1" in combined
    )
    assert "global concurrency cap" in combined
    assert "sl-only" in combined
    assert "tp" in combined and "trailing" in combined
    assert "withdrawal" in combined
    assert "telegram confirmation" in combined
    assert "max_risk_per_grid_usdt: 5" in _read_text(ROOT / "config/risk.yaml")


def test_live_and_telegram_non_capabilities_are_explicit() -> None:
    docs = _docs()
    combined = _combined(docs).lower()
    architecture = docs["docs/CURRENT_ARCHITECTURE_AND_STATUS.md"]
    _require_exact_pairs(
        architecture,
        {
            "create_grid_bot_available": "false",
            "close_grid_bot_available": "false",
            "telegram_runtime_implemented": "false",
            "live_execution_implemented": "false",
            "vps_deployment_implemented": "false",
        },
    )
    _assert_no_positive_claims(
        architecture,
        (
            "create_grid_bot",
            "close_grid_bot",
            "telegram runtime",
            "live execution",
            "vps deployment",
        ),
    )
    assert "create_grid_bot" in combined
    assert "close_grid_bot" in combined
    client = _read_text(ROOT / "src/bybit_grid/bybit/client.py")
    for name in ("create_grid_bot", "close_grid_bot", "private_post"):
        assert f"def {name}" in client


def test_private_validate_boundary_matches_code() -> None:
    docs = _docs()
    combined = _combined(docs)
    source = _read_text(ROOT / "src/bybit_grid/bybit/validate_only.py")
    endpoints = (
        "https://api.bybit.com",
        "/v5/account/info",
        "/v5/account/wallet-balance",
        "/v5/account/fee-rate",
        "/v5/fgridbot/validate",
    )
    assert all(endpoint in source for endpoint in endpoints)
    assert all(endpoint in combined for endpoint in endpoints)
    assert "neutral" in combined.lower() and "geometric" in combined.lower()
    client = _read_text(ROOT / "src/bybit_grid/bybit/client.py")
    assert "trust_env=False" in client
    assert "follow_redirects=False" in client
    assert "generic_private_post_forbidden" in client


def test_env_example_matches_supported_settings_and_safe_defaults() -> None:
    docs = _docs()
    values = _env_values(docs[".env.example"])
    expected = {field.upper() for field in _settings_fields()}
    assert set(values) == expected
    assert values == EXPECTED_ENV_VALUES
    assert not any(key.startswith("TELEGRAM_") for key in values)
    assert not any(
        token in key for key in values for token in ("CREATE", "CLOSE", "DETAIL")
    )


def test_setup_commands_match_python_and_project_metadata() -> None:
    docs = _docs()
    runbook = docs["docs/SETUP_TEST_RUNBOOK.md"]
    metadata = tomllib.loads(_read_text(ROOT / "pyproject.toml"))
    assert metadata["project"]["requires-python"] == ">=3.12"
    assert "Python 3.12+" in runbook
    assert "py -3.12 -m venv .venv" in runbook
    assert "python3.12 -m venv .venv" in runbook
    assert 'python -m pip install -e ".[dev]"' in runbook
    assert "Windows PowerShell" in runbook and "POSIX" in runbook


def test_offline_verification_runbook_is_complete() -> None:
    docs = _docs()
    runbook = docs["docs/SETUP_TEST_RUNBOOK.md"]
    commands = (
        "python scripts/check_numeric_environment.py",
        "python scripts/check_no_live_execution.py",
        "python -m compileall -q src tests scripts",
        "python -m pytest tests -q",
        "python -m pytest -q",
        "ruff check .",
        "python -m pip check",
    )
    assert all(command in runbook for command in commands)
    assert "Do not skip" in runbook or "не " in runbook.lower()


def test_public_data_runbook_distinguishes_owner_network_from_offline_pipeline() -> (
    None
):
    docs = _docs()
    runbook = docs["docs/SETUP_TEST_RUNBOOK.md"]
    assert "Public-data boundary" in runbook
    assert "owner-network" in runbook
    assert "smoke_public_api.py" in runbook
    assert "run_bybit_public_batch_evidence.py" in runbook
    assert "not yet an end-to-end downloader" in runbook
    assert (
        "не требуют credentials" in runbook or "do not require credentials" in runbook
    )


def test_secret_handling_excludes_repo_agents_and_logs() -> None:
    docs = _docs()
    combined = _combined(docs).lower()
    for token in ("chatgpt", "github", "issues", "pr", "logs", "fixtures"):
        assert token in combined
    assert (
        "never commit .env" in combined
        or "не commit" in combined
        or "не помещ" in combined
    )
    assert "withdrawal" in combined
    assert "approved" in combined or "довер" in combined


def test_vps_and_self_hosted_runner_boundary_is_truthful() -> None:
    docs = _docs()
    runbook = docs["docs/SETUP_TEST_RUNBOOK.md"].lower()
    assert "vps" in runbook
    assert "self-hosted runner" in runbook
    assert "not an existing capability" in runbook or "не " in runbook
    workflow = _read_text(ROOT / ".github/workflows/pm-acceptance.yml").lower()
    assert "runs-on: self-hosted" not in workflow
    assert "systemd" not in workflow


def test_troubleshooting_preserves_fail_closed_governance() -> None:
    docs = _docs()
    runbook = docs["docs/SETUP_TEST_RUNBOOK.md"]
    required = (
        "Numeric environment failure",
        "no-live violation",
        "PM scope failure",
        "Pending/failed CI",
        "Data gap/provenance failure",
        "Validate boundary error",
    )
    assert all(item in runbook for item in required)
    assert "never merge unknown status" in runbook
    assert "never fill silently" in runbook
    assert "fail closed" in runbook.lower()


def test_evidence_map_records_completed_governed_lifecycles() -> None:
    docs = _docs()
    evidence = docs["docs/EVIDENCE_MAP.md"]
    expected_numbers = (
        69,
        104,
        110,
        111,
        112,
        113,
        115,
        116,
        117,
        118,
        120,
        121,
        122,
        123,
        125,
        126,
        127,
        128,
        135,
        139,
        140,
        141,
        142,
        143,
    )
    for number in expected_numbers:
        assert f"#{number}" in evidence
    assert "29540177525" in evidence
    assert "29553808388" in evidence
    assert "513 ordinary tests" in evidence
    chains = (
        "06.4C historical plan | #110 / #111 closed unmerged / #112 / #113",
        "06.4D response acceptance | #115 / #116 closed unmerged / #117 / #118",
        "06.4E transcript | #120 / #121 closed unmerged / #122 / #123",
        "06.4F evidence layout | #125 / #126 closed unmerged / #127 / #128",
    )
    assert all(chain in evidence for chain in chains)
    assert "Task #135 merged" in evidence
    assert "Cancellation #139 merged" in evidence
    assert "Frozen erratum #140 merged" in evidence
    assert "Fresh mandatory RED #141 closed Draft and unmerged" in evidence
    assert "Implementation #142 merged" in evidence
    assert "Task-close #143 merged" in evidence


def test_evidence_map_distinguishes_merged_changes_from_closed_red_probes() -> None:
    docs = _docs()
    evidence = docs["docs/EVIDENCE_MAP.md"].lower()
    assert "closed unmerged" in evidence
    assert "red probe success" in evidence
    assert "merge" in evidence
    for number in (111, 116, 121, 126, 141):
        pattern = re.compile(rf"#{number}[^\n]*(closed|unmerged)", re.IGNORECASE)
        assert pattern.search(docs["docs/EVIDENCE_MAP.md"])


def test_evidence_map_marks_pre_control_plane_assurance_gap() -> None:
    docs = _docs()
    evidence = docs["docs/EVIDENCE_MAP.md"]
    assert "PR #1–66" in evidence
    assert all(f"#{number}" in evidence for number in (1, 2, 20, 40, 59, 66))
    assert "#134" in evidence
    assert "not retroactive proof" in evidence
    assert "without executing historical branch code" in evidence


def test_minimal_live_definition_of_done_is_complete_and_unmet() -> None:
    docs = _docs()
    dod = docs["docs/MINIMAL_LIVE_DEFINITION_OF_DONE.md"]
    assert dod.count("- [ ]") >= 20
    assert "- [x] Validate-only P0" in dod
    required = (
        "canonical store",
        "semantic neutral geometric replay",
        "5 USDT",
        "500 USDT",
        "one grid per instrument",
        "global cap 1",
        "no_policy_passes",
        "#133",
        "#134",
        "no withdrawal permission",
        "manual Telegram confirmation",
        "Emergency stop",
        "VPS/self-hosted runner",
        "100 confirmed operations",
    )
    assert all(item.lower() in dod.lower() for item in required)
    checked = re.findall(r"^- \[x\] (.+)$", dod, flags=re.MULTILINE)
    assert checked == ["Validate-only P0 transport boundary completed by #142/#143."]
    _require_exact_pairs(
        dod,
        {
            **RISK_PAIRS,
            "current_minimal_live_ready": "false",
            "live_execution_authorized": "false",
        },
    )
    _assert_no_positive_claims(
        dod,
        ("withdrawal", "live trading", "live execution", "minimal live"),
    )
    assert "Current verdict: Minimal-live DoD is unmet" in dod
    assert "No live trading is authorized" in dod


def test_markdown_links_and_referenced_paths_resolve() -> None:
    docs = _docs()
    checked = 0
    for path, text in docs.items():
        if not path.endswith(".md"):
            continue
        source_dir = (ROOT / path).parent
        for _label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0]
            assert clean
            resolved = (source_dir / clean).resolve()
            assert resolved == ROOT or ROOT in resolved.parents, (path, target)
            assert resolved.is_file(), (path, target)
            checked += 1
    assert checked >= 15
    referenced = (
        "pm_acceptance/active_task.json",
        "scripts/check_numeric_environment.py",
        "scripts/check_no_live_execution.py",
        "src/bybit_grid/bybit/validate_only.py",
        "src/bybit_grid/bybit/client.py",
    )
    assert all((ROOT / path).is_file() for path in referenced)
