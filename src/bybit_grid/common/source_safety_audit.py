from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

FGRID_PREFIX = "/v5/" + "fgridbot/"
ORDER_PREFIX = "/v5/" + "order/"
BANNED_ENDPOINTS = {
    FGRID_PREFIX + "create",
    FGRID_PREFIX + "close",
    ORDER_PREFIX + "create",
    ORDER_PREFIX + "cancel",
    ORDER_PREFIX + "create-batch",
    ORDER_PREFIX + "cancel-batch",
    ORDER_PREFIX + "amend-batch",
}
BATCH_ENDPOINT_MARKERS = (ORDER_PREFIX, "batch")


@dataclass
class SafetyAuditResult:
    ok: bool
    scanned_files: int
    violations: list[str] = field(default_factory=list)


def _python_files(roots: list[Path]) -> list[Path]:
    return sorted(p for r in roots if r.exists() for p in r.rglob("*.py"))


def _literal_str(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _function_raises_not_implemented(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Raise):
            exc = child.exc
            if isinstance(exc, ast.Call) and getattr(exc.func, "id", "") == "NotImplementedError":
                return True
            if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
                return True
    return False


def _is_private_post_call(node: ast.Call) -> bool:
    return isinstance(node.func, ast.Attribute) and node.func.attr == "private_post"


def _called_endpoint(node: ast.Call) -> str | None:
    if node.args:
        return _literal_str(node.args[0])
    for kw in node.keywords:
        if kw.arg in {"endpoint", "path"}:
            return _literal_str(kw.value)
    return None


def _audit_tree(path: Path, tree: ast.AST) -> list[str]:
    violations: list[str] = []
    placeholders = {"create_grid_bot": False, "close_grid_bot": False}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in placeholders:
            placeholders[node.name] = _function_raises_not_implemented(node)
        if isinstance(node, ast.Call) and _is_private_post_call(node):
            endpoint = _called_endpoint(node)
            if endpoint in BANNED_ENDPOINTS or (
                endpoint and all(marker in endpoint for marker in BATCH_ENDPOINT_MARKERS)
            ):
                violations.append(f"{path}: private POST to forbidden endpoint {endpoint}")
    for name, ok in placeholders.items():
        if name in {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))} and not ok:
            violations.append(f"{path}: {name} must raise NotImplementedError")
    return violations


def audit_source_tree(repo_root: Path | str = ".") -> SafetyAuditResult:
    root = Path(repo_root)
    violations: list[str] = []
    files = _python_files([root / "src" / "bybit_grid", root / "scripts"])
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            violations.append(f"{path}: syntax error: {exc}")
            continue
        violations.extend(_audit_tree(path, tree))
    try:
        from bybit_grid.config import Settings
        s = Settings(_env_file=None)
        if s.live_trading_enabled is not False:
            violations.append("LIVE_TRADING_ENABLED default must be false")
        if s.allow_live_trading != "NO":
            violations.append("ALLOW_LIVE_TRADING default must be NO")
    except Exception as exc:  # pragma: no cover
        violations.append(f"could not inspect Settings defaults: {exc}")
    return SafetyAuditResult(ok=not violations, scanned_files=len(files), violations=violations)
