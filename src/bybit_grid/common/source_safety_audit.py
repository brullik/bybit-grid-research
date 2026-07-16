from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


CLIENT_PATH = "src/bybit_grid/bybit/client.py"
SAMPLE_PATH = "scripts/validate_sample_grid.py"
UNIVERSE_PATH = "scripts/validate_universe_fgrid_constraints.py"

GENERIC_POST_MESSAGE = "generic private_post call is forbidden"
DYNAMIC_POST_MESSAGE = "dynamic lookup of private_post is forbidden"
EXTERNAL_POST_MESSAGE = "HTTP POST outside canonical client transport is forbidden"
TRANSPORT_SHAPE_MESSAGE = "canonical validate transport shape is required"
UNIVERSE_PREFLIGHT_MESSAGE = (
    "validate universe policy preflight must precede credentials and threads"
)
UNIVERSE_WORKER_MESSAGE = "validate universe workers must use preflighted settings"
SAMPLE_PREFLIGHT_MESSAGE = "validate sample policy preflight must precede side effects"
BOUNDARY_HANDLER_MESSAGE = "validate-only boundary error must be re-raised before broad handler"


@dataclass
class SafetyAuditResult:
    ok: bool
    scanned_files: int
    violations: list[str] = field(default_factory=list)


def _python_files(roots: list[Path]) -> list[Path]:
    return sorted(path for root in roots if root.exists() for path in root.rglob("*.py"))


def _has_suffix(path: Path, suffix: str) -> bool:
    return path.as_posix().endswith(suffix)


def _top_level_functions(
    tree: ast.AST,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in getattr(tree, "body", ())
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _function_nodes(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterable[ast.AST]:
    def descend(node: ast.AST) -> Iterable[ast.AST]:
        yield node
        for child in ast.iter_child_nodes(node):
            yield from descend(child)

    for statement in function.body:
        yield from descend(statement)


def _function_calls(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    return [node for node in _function_nodes(function) if isinstance(node, ast.Call)]


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _meaningful_body(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.stmt]:
    body = list(function.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and type(body[0].value.value) is str
    ):
        body.pop(0)
    return body


def _is_direct_not_implemented(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Raise):
        return False
    expression = statement.exc
    if isinstance(expression, ast.Call):
        expression = expression.func
    return isinstance(expression, ast.Name) and expression.id == "NotImplementedError"


def _is_dynamic_private_post_lookup(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Name)
        and call.func.id == "getattr"
        and len(call.args) >= 2
        and isinstance(call.args[1], ast.Constant)
        and type(call.args[1].value) is str
        and call.args[1].value == "private_post"
    )


def _is_dynamic_http_post_lookup(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Name)
        and call.func.id == "getattr"
        and len(call.args) >= 2
        and isinstance(call.args[1], ast.Constant)
        and type(call.args[1].value) is str
        and call.args[1].value == "post"
    )


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name):
        return handler.type.id in {"Exception", "BaseException"}
    if isinstance(handler.type, ast.Tuple):
        return any(
            isinstance(value, ast.Name) and value.id in {"Exception", "BaseException"}
            for value in handler.type.elts
        )
    return False


def _is_boundary_reraise(handler: ast.ExceptHandler) -> bool:
    return (
        isinstance(handler.type, ast.Name)
        and handler.type.id == "ValidateOnlyBoundaryError"
        and len(handler.body) == 1
        and isinstance(handler.body[0], ast.Raise)
        and handler.body[0].exc is None
    )


def _try_calls_validate(try_node: ast.Try) -> bool:
    for statement in try_node.body:
        for node in ast.walk(statement):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "validate_grid_bot"
            ):
                return True
    return False


def _audit_boundary_handlers(
    path: Path,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    violations: list[str] = []
    for node in _function_nodes(function):
        if not isinstance(node, ast.Try) or not _try_calls_validate(node):
            continue
        broad_indexes = [
            index for index, handler in enumerate(node.handlers) if _is_broad_handler(handler)
        ]
        if not broad_indexes:
            continue
        safe_indexes = [
            index for index, handler in enumerate(node.handlers) if _is_boundary_reraise(handler)
        ]
        if not safe_indexes or min(safe_indexes) >= min(broad_indexes):
            violations.append(f"{path}:{node.lineno}: {BOUNDARY_HANDLER_MESSAGE}")
    return violations


def _canonical_post_shape(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    positional = (*function.args.posonlyargs, *function.args.args)
    if (
        [argument.arg for argument in positional] != ["self", "prepared"]
        or function.args.vararg is not None
        or function.args.kwarg is not None
        or function.args.kwonlyargs
        or function.args.defaults
        or any(value is not None for value in function.args.kw_defaults)
    ):
        return False
    posts = [
        node
        for node in _function_nodes(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
    ]
    if len(posts) != 1:
        return False
    post = posts[0]
    keywords = {keyword.arg: keyword.value for keyword in post.keywords}
    return (
        isinstance(post.func.value, ast.Attribute)
        and isinstance(post.func.value.value, ast.Name)
        and post.func.value.value.id == "self"
        and post.func.value.attr == "private_http"
        and len(post.args) == 1
        and isinstance(post.args[0], ast.Name)
        and post.args[0].id == "CANONICAL_FGRID_VALIDATE_ENDPOINT"
        and set(keywords) == {"content", "headers"}
        and isinstance(keywords["content"], ast.Attribute)
        and isinstance(keywords["content"].value, ast.Name)
        and keywords["content"].value.id == "prepared"
        and keywords["content"].attr == "json_body"
        and isinstance(keywords["headers"], ast.Name)
        and keywords["headers"].id == "headers"
    )


def _audit_client(path: Path, tree: ast.AST) -> tuple[list[str], set[int]]:
    violations: list[str] = []
    allowed_posts: set[int] = set()
    client_classes = [
        node
        for node in getattr(tree, "body", ())
        if isinstance(node, ast.ClassDef) and node.name == "BybitClient"
    ]
    helpers: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for client_class in client_classes:
        for node in client_class.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[node.name] = node
                if node.name == "_private_validate_post":
                    helpers.append(node)
    if len(helpers) != 1 or not _canonical_post_shape(helpers[0]):
        violations.append(f"{path}: {TRANSPORT_SHAPE_MESSAGE}")
    else:
        allowed_posts.update(
            id(node)
            for node in _function_nodes(helpers[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "post"
        )
    for name in ("create_grid_bot", "close_grid_bot"):
        method = methods.get(name)
        if (
            method is None
            or method.decorator_list
            or len(_meaningful_body(method)) != 1
            or not _is_direct_not_implemented(_meaningful_body(method)[0])
        ):
            violations.append(
                f"{path}: {name} must be immediate unconditional NotImplementedError stub"
            )
    return violations, allowed_posts


def _policy_preflight_calls(calls: list[ast.Call]) -> list[ast.Call]:
    return [
        call
        for call in calls
        if isinstance(call.func, ast.Name)
        and call.func.id
        in {"enforce_validate_only_settings", "_enforce_validate_only_settings"}
        and any(
            keyword.arg == "settings" and isinstance(keyword.value, ast.Name)
            for keyword in call.keywords
        )
    ]


def _unconditional_policy_preflight_calls(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for statement in _meaningful_body(function):
        if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
            continue
        call = statement.value
        if _policy_preflight_calls([call]):
            calls.append(call)
    return calls


def _preflight_immediately_follows_settings_load(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    body = _meaningful_body(function)
    loads: list[tuple[int, str]] = []
    preflights: list[tuple[int, ast.Call]] = []
    for index, statement in enumerate(body):
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(statement.value, ast.Call)
            and _called_name(statement.value) == "load_settings"
        ):
            loads.append((index, statement.targets[0].id))
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and _policy_preflight_calls([statement.value])
        ):
            preflights.append((index, statement.value))
    if len(loads) != 1 or len(preflights) != 1:
        return False
    load_index, settings_name = loads[0]
    preflight_index, preflight = preflights[0]
    if preflight_index != load_index + 1:
        return False
    return any(
        keyword.arg == "settings"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == settings_name
        for keyword in preflight.keywords
    )


def _audit_sample(path: Path, tree: ast.AST) -> list[str]:
    functions = _top_level_functions(tree)
    main = functions.get("main")
    if main is None:
        return [f"{path}: {SAMPLE_PREFLIGHT_MESSAGE}"]
    violations = _audit_boundary_handlers(path, main)
    calls = _function_calls(main)
    all_preflights = _policy_preflight_calls(calls)
    preflights = _unconditional_policy_preflight_calls(main)
    side_effect_names = {
        "Path",
        "_market_numbers",
        "_refusal_reason",
        "_write_json",
        "build_fgrid_validate_payload",
        "BybitClient",
        "read_text",
        "static_payload",
        "utc_now_iso",
        "write_sprint_report",
    }
    load_calls = [call for call in calls if _called_name(call) == "load_settings"]
    side_effects = [call for call in calls if _called_name(call) in side_effect_names]
    if (
        len(all_preflights) != 1
        or len(preflights) != 1
        or len(load_calls) != 1
        or not _preflight_immediately_follows_settings_load(main)
    ):
        violations.append(f"{path}: {SAMPLE_PREFLIGHT_MESSAGE}")
        return violations
    preflight_line = preflights[0].lineno
    if preflight_line <= load_calls[0].lineno or any(
        preflight_line >= call.lineno for call in side_effects
    ):
        violations.append(f"{path}: {SAMPLE_PREFLIGHT_MESSAGE}")
    return violations


def _reachable_worker_functions(
    worker: ast.FunctionDef | ast.AsyncFunctionDef,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    reached: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    pending = [worker]
    seen: set[str] = set()
    while pending:
        function = pending.pop()
        if function.name in seen:
            continue
        seen.add(function.name)
        reached.append(function)
        for call in _function_calls(function):
            if isinstance(call.func, ast.Name) and call.func.id in functions:
                pending.append(functions[call.func.id])
    return reached


def _worker_reloads_configuration(
    worker: ast.FunctionDef | ast.AsyncFunctionDef,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
) -> bool:
    forbidden_calls = {
        "Settings",
        "build_fgrid_validate_payload",
        "build_min_sweep_candidates",
        "getenv",
        "load_settings",
    }
    for function in _reachable_worker_functions(worker, functions):
        if any(_called_name(call) in forbidden_calls for call in _function_calls(function)):
            return True
        if any(
            isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}
            for node in _function_nodes(function)
        ):
            return True
    return False


def _audit_universe(path: Path, tree: ast.AST) -> list[str]:
    functions = _top_level_functions(tree)
    violations: list[str] = []
    main = functions.get("main")
    worker = functions.get("_validate_symbol")
    safe_worker_parameters: set[str] = set()

    if main is None:
        violations.append(f"{path}: {UNIVERSE_PREFLIGHT_MESSAGE}")
    else:
        calls = _function_calls(main)
        all_preflights = _policy_preflight_calls(calls)
        preflights = _unconditional_policy_preflight_calls(main)
        protected_calls = [
            call
            for call in calls
            if _called_name(call)
            in {
                "Path",
                "_plan",
                "build_universe",
                "existing_keys",
                "purge_skipped_constraints",
                "read_parquet",
                "require_private_credentials",
                "ThreadPoolExecutor",
            }
        ]
        if (
            len(all_preflights) != 1
            or len(preflights) != 1
            or not _preflight_immediately_follows_settings_load(main)
            or any(preflights[0].lineno >= call.lineno for call in protected_calls)
        ):
            violations.append(f"{path}: {UNIVERSE_PREFLIGHT_MESSAGE}")

    if worker is None:
        violations.append(f"{path}: {UNIVERSE_WORKER_MESSAGE}")
    else:
        violations.extend(_audit_boundary_handlers(path, worker))
        worker_parameters = {
            argument.arg for argument in (*worker.args.posonlyargs, *worker.args.args)
        }
        bybit_calls = [
            call
            for call in _function_calls(worker)
            if isinstance(call.func, ast.Name) and call.func.id == "BybitClient"
        ]
        safe_worker_parameters = {
            call.args[0].id
            for call in bybit_calls
            if call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id in worker_parameters
        }
        if (
            not safe_worker_parameters
            or _worker_reloads_configuration(worker, functions)
        ):
            violations.append(f"{path}: {UNIVERSE_WORKER_MESSAGE}")

    if main is not None and worker is not None:
        submissions = [
            call
            for call in _function_calls(main)
            if isinstance(call.func, ast.Attribute)
            and call.func.attr == "submit"
            and call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id == "_validate_symbol"
        ]
        if submissions and any(
            not any(
                isinstance(argument, ast.Name) and argument.id in safe_worker_parameters
                for argument in call.args[1:]
            )
            for call in submissions
        ):
            violations.append(f"{path}: {UNIVERSE_WORKER_MESSAGE}")
    return violations


def _audit_tree(path: Path, tree: ast.AST) -> list[str]:
    violations: list[str] = []
    allowed_posts: set[int] = set()
    if _has_suffix(path, CLIENT_PATH):
        client_violations, allowed_posts = _audit_client(path, tree)
        violations.extend(client_violations)
    if _has_suffix(path, SAMPLE_PATH):
        violations.extend(_audit_sample(path, tree))
    if _has_suffix(path, UNIVERSE_PATH):
        violations.extend(_audit_universe(path, tree))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "private_post":
            violations.append(f"{path}:{node.lineno}: {GENERIC_POST_MESSAGE}")
        if _is_dynamic_private_post_lookup(node):
            violations.append(f"{path}:{node.lineno}: {DYNAMIC_POST_MESSAGE}")
        if _is_dynamic_http_post_lookup(node):
            violations.append(f"{path}:{node.lineno}: {EXTERNAL_POST_MESSAGE}")
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "post"
            and id(node) not in allowed_posts
        ):
            violations.append(f"{path}:{node.lineno}: {EXTERNAL_POST_MESSAGE}")
    return violations


def audit_source_tree(repo_root: Path | str = ".") -> SafetyAuditResult:
    root = Path(repo_root)
    violations: list[str] = []
    files = _python_files([root / "src" / "bybit_grid", root / "scripts"])
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError) as exc:
            violations.append(f"{path}: source inspection failed: {exc}")
            continue
        violations.extend(_audit_tree(path, tree))
    try:
        from bybit_grid.config import Settings

        settings = Settings(_env_file=None)
        if settings.live_trading_enabled is not False:
            violations.append("LIVE_TRADING_ENABLED default must be false")
        if settings.allow_live_trading != "NO":
            violations.append("ALLOW_LIVE_TRADING default must be NO")
    except Exception as exc:  # pragma: no cover
        violations.append(f"could not inspect Settings defaults: {exc}")
    return SafetyAuditResult(
        ok=not violations,
        scanned_files=len(files),
        violations=violations,
    )
