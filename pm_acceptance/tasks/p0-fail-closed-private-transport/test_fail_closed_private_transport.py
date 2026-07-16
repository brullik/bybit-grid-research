from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields, is_dataclass
from decimal import Decimal
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import textwrap

import httpx
import pytest
from pydantic import ValidationError


MODULE_NAME = "bybit_grid.bybit.validate_only"
UNAVAILABLE = "validate_only_boundary_unavailable"
CANONICAL_ENDPOINT = "/v5/fgridbot/validate"
CANONICAL_BASE_URL = "https://api.bybit.com"
PRIVATE_GET_ENDPOINTS = (
    "/v5/account/info",
    "/v5/account/wallet-balance",
    "/v5/account/fee-rate",
)
EXPECTED_POLICY_SURFACE = (
    "CANONICAL_BYBIT_ENV",
    "CANONICAL_BYBIT_API_BASE_URL",
    "CANONICAL_PRIVATE_GET_ENDPOINTS",
    "CANONICAL_FGRID_VALIDATE_ENDPOINT",
    "CANONICAL_FGRID_GRID_MODE_NEUTRAL",
    "CANONICAL_FGRID_GRID_TYPE_GEOMETRIC",
    "ValidateOnlyBoundaryError",
    "enforce_validate_only_settings",
    "enforce_private_get_request",
    "enforce_validate_only_payload",
)
EXPECTED_PAYLOAD_KEYS = {
    "symbol",
    "leverage",
    "grid_mode",
    "grid_type",
    "min_price",
    "max_price",
    "cell_number",
    "init_margin",
    "stop_loss_price",
}
POLICY_ENV_KEYS = (
    "BYBIT_ENV",
    "BYBIT_API_BASE_URL",
    "BYBIT_FGRID_VALIDATE_PATH",
    "BYBIT_FGRID_GRID_MODE_NEUTRAL",
    "BYBIT_FGRID_GRID_TYPE_GEOMETRIC",
    "BYBIT_RECV_WINDOW",
    "GRID_VALIDATE_ENABLED",
    "LIVE_TRADING_ENABLED",
    "ALLOW_LIVE_TRADING",
)


def _api():
    try:
        module = importlib.import_module(MODULE_NAME)
    except ModuleNotFoundError as caught:
        if caught.name != MODULE_NAME:
            raise
        raise RuntimeError(UNAVAILABLE) from caught
    if any(not hasattr(module, name) for name in (*EXPECTED_POLICY_SURFACE, "__all__")):
        raise RuntimeError(UNAVAILABLE)
    _install_repo_universe_script(module)
    return module


def _client_api():
    return importlib.import_module("bybit_grid.bybit.client")


def _payload_api():
    return importlib.import_module("bybit_grid.bybit.fgrid_payloads")


def _audit_api():
    return importlib.import_module("bybit_grid.common.source_safety_audit")


def _config_api():
    return importlib.import_module("bybit_grid.config")


def _install_repo_universe_script(policy_module) -> None:
    module_name = "scripts.validate_universe_fgrid_constraints"
    if module_name in sys.modules:
        return
    repo_root = Path(policy_module.__file__).resolve(strict=True).parents[3]
    path = (repo_root / "scripts/validate_universe_fgrid_constraints.py").resolve(
        strict=True
    )
    scripts_package = importlib.import_module("scripts")
    scripts_path = str(path.parent)
    appended = scripts_path not in scripts_package.__path__
    if appended:
        scripts_package.__path__.append(scripts_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("could_not_load_repo_script:validate_universe_fgrid_constraints")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loaded = False
    try:
        spec.loader.exec_module(module)
        loaded = True
    finally:
        if appended:
            scripts_package.__path__.remove(scripts_path)
        if not loaded:
            sys.modules.pop(module_name, None)


def _payload() -> dict[str, object]:
    return {
        "symbol": "BTCUSDT",
        "leverage": "1",
        "grid_mode": 1,
        "grid_type": 2,
        "min_price": "58500",
        "max_price": "71500",
        "cell_number": 10,
        "init_margin": "100",
        "stop_loss_price": "55250",
    }


def _settings(**overrides):
    values = {
        "bybit_env": "mainnet",
        "bybit_api_base_url": CANONICAL_BASE_URL,
        "bybit_api_key": "test-key-not-a-secret",
        "bybit_api_secret": "test-secret-not-a-secret",
        "bybit_fgrid_validate_path": CANONICAL_ENDPOINT,
        "bybit_fgrid_grid_mode_neutral": 1,
        "bybit_fgrid_grid_type_geometric": 2,
        "bybit_recv_window": 5000,
        "grid_validate_enabled": True,
        "live_trading_enabled": False,
        "allow_live_trading": "NO",
    }
    values.update(overrides)
    return _config_api().Settings(_env_file=None, **values)


class _Limiter:
    def __init__(self, events: list[str]):
        self.events = events

    def wait(self):
        self.events.append("rate_limit")


class _MutatingLimiter:
    def __init__(self, events: list[str], mutation):
        self.events = events
        self.mutation = mutation

    def wait(self):
        self.events.append("rate_limit")
        self.mutation()


class _OriginDriftLimiter:
    def __init__(self, events: list[str], private_http: _Http):
        self.events = events
        self.private_http = private_http

    def wait(self):
        self.events.append("rate_limit")
        self.private_http.base_url = httpx.URL("https://attacker.invalid")


class _Http:
    def __init__(self, events: list[str]):
        self.events = events
        self.calls: list[tuple[object, object, object]] = []
        self.base_url = httpx.URL(CANONICAL_BASE_URL)
        self.follow_redirects = False
        self._trust_env = False

    def post(self, endpoint, *, content, headers):
        self.events.append("http")
        self.calls.append((endpoint, content, headers))
        request = httpx.Request("POST", f"https://api.bybit.com{endpoint}")
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"checkCode": "0"}},
            request=request,
        )

    def get(self, endpoint, *, params, headers):
        self.events.append("http")
        self.calls.append((endpoint, params, dict(headers)))
        request = httpx.Request("GET", f"https://api.bybit.com{endpoint}")
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {}},
            request=request,
        )


class _FailingHttp(_Http):
    def __init__(self, events: list[str], on_first=None):
        super().__init__(events)
        self.on_first = on_first

    def post(self, endpoint, *, content, headers):
        self.events.append("http")
        self.calls.append((endpoint, content, headers))
        if len(self.calls) == 1 and self.on_first is not None:
            self.on_first()
        request = httpx.Request("POST", f"https://api.bybit.com{endpoint}")
        raise httpx.ConnectError("injected retryable transport failure", request=request)


class _FailingGetHttp(_Http):
    def __init__(self, events: list[str], on_first=None):
        super().__init__(events)
        self.on_first = on_first

    def get(self, endpoint, *, params, headers):
        self.events.append("http")
        self.calls.append((endpoint, params, dict(headers)))
        if len(self.calls) == 1 and self.on_first is not None:
            self.on_first()
        request = httpx.Request("GET", f"https://api.bybit.com{endpoint}")
        raise httpx.ConnectError("injected retryable transport failure", request=request)


class _RetryOnceHttp(_Http):
    def post(self, endpoint, *, content, headers):
        self.events.append("http")
        self.calls.append((endpoint, content, headers))
        request = httpx.Request("POST", f"https://api.bybit.com{endpoint}")
        if len(self.calls) == 1:
            raise httpx.ConnectError("injected first-attempt failure", request=request)
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"checkCode": "0"}},
            request=request,
        )

    def get(self, endpoint, *, params, headers):
        self.events.append("http")
        self.calls.append((endpoint, params, dict(headers)))
        request = httpx.Request("GET", f"https://api.bybit.com{endpoint}")
        if len(self.calls) == 1:
            raise httpx.ConnectError("injected first-attempt failure", request=request)
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {}},
            request=request,
        )


def _client(settings, events: list[str], http=None):
    client_api = _client_api()
    value = object.__new__(client_api.BybitClient)
    value.settings = settings
    value.rate_limiter = _Limiter(events)
    value.stats = client_api.BybitClientStats()
    value.http = _Http(events)
    value.private_http = _Http(events) if http is None else http
    return value


def _assert_boundary_error(api, code: str, operation) -> None:
    with pytest.raises(api.ValidateOnlyBoundaryError) as caught:
        operation()
    assert str(caught.value) == code


def _clear_policy_environment(monkeypatch) -> None:
    for name in POLICY_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)


def _build_payload(payload_api):
    return payload_api.build_fgrid_validate_payload(
        "BTCUSDT",
        Decimal("65000"),
        Decimal("0.1"),
        leverage=1,
        cell_number=10,
        init_margin="100",
        lower_mult=Decimal("0.90"),
        upper_mult=Decimal("1.10"),
        stop_loss_mult=Decimal("0.85"),
    )


def _meaningful_body(node: ast.FunctionDef) -> list[ast.stmt]:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and type(body[0].value.value) is str
    ):
        body.pop(0)
    return body


def _is_direct_not_implemented_raise(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.Raise):
        return False
    expression = statement.exc
    if isinstance(expression, ast.Call):
        expression = expression.func
    return isinstance(expression, ast.Name) and expression.id == "NotImplementedError"


def _write_source(root: Path, relative_path: str, source: str) -> None:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(source), encoding="utf-8")


def _assert_boundary_reraised_before_broad(function: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    guarded_tries: list[ast.Try] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Try):
            continue
        body_nodes = [child for statement in node.body for child in ast.walk(statement)]
        if any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "validate_grid_bot"
            for child in body_nodes
        ):
            guarded_tries.append(node)
    assert guarded_tries
    for guarded_try in guarded_tries:
        handler_names = [
            handler.type.id if isinstance(handler.type, ast.Name) else None
            for handler in guarded_try.handlers
        ]
        assert "ValidateOnlyBoundaryError" in handler_names
        boundary_index = handler_names.index("ValidateOnlyBoundaryError")
        boundary_handler = guarded_try.handlers[boundary_index]
        assert len(boundary_handler.body) == 1
        assert isinstance(boundary_handler.body[0], ast.Raise)
        assert boundary_handler.body[0].exc is None
        broad_indexes = [
            index
            for index, name in enumerate(handler_names)
            if name in {None, "Exception", "BaseException"}
        ]
        assert all(boundary_index < index for index in broad_indexes)


def test_exact_policy_surface_constants_signatures_and_error_base():
    api = _api()
    assert api.__all__ == EXPECTED_POLICY_SURFACE
    assert issubclass(api.ValidateOnlyBoundaryError, PermissionError)
    assert type(api.CANONICAL_BYBIT_ENV) is str
    assert api.CANONICAL_BYBIT_ENV == "mainnet"
    assert type(api.CANONICAL_BYBIT_API_BASE_URL) is str
    assert api.CANONICAL_BYBIT_API_BASE_URL == CANONICAL_BASE_URL
    assert type(api.CANONICAL_PRIVATE_GET_ENDPOINTS) is tuple
    assert api.CANONICAL_PRIVATE_GET_ENDPOINTS == PRIVATE_GET_ENDPOINTS
    assert all(type(value) is str for value in api.CANONICAL_PRIVATE_GET_ENDPOINTS)
    assert type(api.CANONICAL_FGRID_VALIDATE_ENDPOINT) is str
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT
    assert type(api.CANONICAL_FGRID_GRID_MODE_NEUTRAL) is int
    assert api.CANONICAL_FGRID_GRID_MODE_NEUTRAL == 1
    assert type(api.CANONICAL_FGRID_GRID_TYPE_GEOMETRIC) is int
    assert api.CANONICAL_FGRID_GRID_TYPE_GEOMETRIC == 2
    for name, parameter_names in (
        ("enforce_validate_only_settings", ("settings",)),
        ("enforce_private_get_request", ("endpoint", "params")),
        ("enforce_validate_only_payload", ("payload",)),
    ):
        signature = inspect.signature(getattr(api, name))
        assert tuple(signature.parameters) == parameter_names
        for parameter_name in parameter_names:
            parameter = signature.parameters[parameter_name]
            assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
            assert parameter.default is inspect.Parameter.empty


def test_policy_module_has_no_external_authority_import_or_import_time_call():
    api = _api()
    tree = ast.parse(inspect.getsource(api))
    forbidden = {
        "asyncio",
        "datetime",
        "http",
        "httpx",
        "multiprocessing",
        "os",
        "pathlib",
        "random",
        "requests",
        "secrets",
        "socket",
        "ssl",
        "subprocess",
        "threading",
        "time",
        "tenacity",
        "urllib",
    }
    imported: set[str] = set()
    imported_full: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
            imported_full.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
            imported_full.add(node.module)
    assert imported.isdisjoint(forbidden)
    assert not any(
        module == "signing"
        or module == "rate_limit"
        or module.endswith(".signing")
        or module.endswith(".rate_limit")
        for module in imported_full
    )
    for node in tree.body:
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Constant)
            assert type(node.value.value) is str
            continue
        assert isinstance(
            node,
            (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.ClassDef, ast.FunctionDef),
        )
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            assert not any(isinstance(child, ast.Call) for child in ast.walk(node.value))
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            assert not any(
                isinstance(child, ast.Call)
                for decorator in node.decorator_list
                for child in ast.walk(decorator)
            )
        if isinstance(node, ast.FunctionDef):
            defaults = (*node.args.defaults, *node.args.kw_defaults)
            assert not any(
                isinstance(child, ast.Call)
                for default in defaults
                if default is not None
                for child in ast.walk(default)
            )


def test_settings_guard_requires_exact_model_and_accepts_only_locked_state():
    api = _api()
    settings = _settings()
    assert api.enforce_validate_only_settings(settings=settings) is None
    for removed_name in (
        "bybit_fgrid_create_path",
        "bybit_fgrid_close_path",
        "bybit_fgrid_detail_path",
    ):
        assert not hasattr(settings, removed_name)
    for value in (None, object(), {}, _payload()):
        _assert_boundary_error(
            api,
            "validate_settings_not_exact",
            lambda value=value: api.enforce_validate_only_settings(settings=value),
        )

    class DerivedSettings(_config_api().Settings):
        pass

    derived = DerivedSettings(
        _env_file=None,
        bybit_fgrid_validate_path=CANONICAL_ENDPOINT,
        bybit_fgrid_grid_mode_neutral=1,
        bybit_fgrid_grid_type_geometric=2,
        grid_validate_enabled=True,
        live_trading_enabled=False,
        allow_live_trading="NO",
    )
    _assert_boundary_error(
        api,
        "validate_settings_not_exact",
        lambda: api.enforce_validate_only_settings(settings=derived),
    )

    ordered_invalid = (
        ("bybit_env", "testnet", "validate_environment_forbidden"),
        ("bybit_api_base_url", "https://attacker.invalid", "validate_api_base_url_forbidden"),
        ("bybit_fgrid_validate_path", "/v5/order/create", "validate_endpoint_forbidden"),
        ("bybit_fgrid_grid_mode_neutral", 0, "validate_grid_mode_forbidden"),
        ("bybit_fgrid_grid_type_geometric", 1, "validate_grid_type_forbidden"),
        ("bybit_recv_window", 4999, "validate_recv_window_forbidden"),
        ("grid_validate_enabled", 1, "validate_enabled_flag_invalid"),
        ("live_trading_enabled", True, "validate_live_authority_forbidden"),
    )
    for first_index, (_, _, expected_code) in enumerate(ordered_invalid):
        candidate = _settings()
        for field_name, bad_value, _ in ordered_invalid[first_index:]:
            object.__setattr__(candidate, field_name, bad_value)
        _assert_boundary_error(
            api,
            expected_code,
            lambda candidate=candidate: api.enforce_validate_only_settings(settings=candidate),
        )


def test_environment_origin_and_httpx_proxy_tls_environment_are_fail_closed(monkeypatch):
    api = _api()

    class Text(str):
        pass

    for value in ("testnet", "demo", "MAINNET", Text("mainnet"), None):
        settings = _settings()
        object.__setattr__(settings, "bybit_env", value)
        _assert_boundary_error(
            api,
            "validate_environment_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )
    for value in (
        "",
        "http://api.bybit.com",
        "https://api-testnet.bybit.com",
        "https://api.bytbit.com",
        "https://api.bybit.com/",
        "https://api.bybit.com/v5",
        "https://api.bybit.com?x=1",
        "https://api.bybit.com#x",
        "https://user@api.bybit.com",
        "https://api.bybit.com:443",
        "//api.bybit.com",
        "https://localhost",
        "https://127.0.0.1",
        b"https://api.bybit.com",
        Text(CANONICAL_BASE_URL),
        None,
    ):
        settings = _settings()
        object.__setattr__(settings, "bybit_api_base_url", value)
        _assert_boundary_error(
            api,
            "validate_api_base_url_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )

    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    ):
        monkeypatch.setenv(name, "https://attacker.invalid")
    captured: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeHttpClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.closed = False
            captured.append((args, kwargs))

        def close(self):
            self.closed = True

    client_api = _client_api()
    monkeypatch.setattr(client_api.httpx, "Client", FakeHttpClient)
    client = client_api.BybitClient(_settings())
    assert len(captured) == 2
    assert client.http is not client.private_http
    assert type(client.private_http.kwargs["base_url"]) is str
    assert client.private_http.kwargs["base_url"] == CANONICAL_BASE_URL
    assert all(kwargs["trust_env"] is False for args, kwargs in captured)
    assert all(kwargs["follow_redirects"] is False for args, kwargs in captured)
    assert any(kwargs["base_url"] == CANONICAL_BASE_URL for args, kwargs in captured)
    client.close()
    assert client.http.closed is True
    assert client.private_http.closed is True
    tree = ast.parse(textwrap.dedent(inspect.getsource(client_api.BybitClient.__init__)))
    constructors = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Client"
    ]
    assert len(constructors) == 2
    for constructor in constructors:
        trust_env = [kw.value for kw in constructor.keywords if kw.arg == "trust_env"]
        assert len(trust_env) == 1
        assert isinstance(trust_env[0], ast.Constant)
        assert trust_env[0].value is False
        follow_redirects = [
            kw.value for kw in constructor.keywords if kw.arg == "follow_redirects"
        ]
        assert len(follow_redirects) == 1
        assert isinstance(follow_redirects[0], ast.Constant)
        assert follow_redirects[0].value is False


def test_endpoint_alias_absolute_query_malformed_and_subclass_values_fail_closed():
    api = _api()

    class Text(str):
        pass

    variants = (
        None,
        b"/v5/fgridbot/validate",
        "",
        " /v5/fgridbot/validate",
        "/v5/fgridbot/validate ",
        "v5/fgridbot/validate",
        "//v5/fgridbot/validate",
        "/v5//fgridbot/validate",
        "/v5/fgridbot/./validate",
        "/v5/fgridbot/validate/",
        "/V5/fgridbot/validate",
        "/v5/fgridbot/validate?category=linear",
        "/v5/fgridbot/validate#fragment",
        "https://api.bybit.com/v5/fgridbot/validate",
        "//api.bybit.com/v5/fgridbot/validate",
        "/v5/fgridbot/create",
        "/v5/fgridbot/close",
        "/v5/fgridbot/detail",
        "/v5/order/create",
        "/v5/asset/withdraw/create",
        Text(CANONICAL_ENDPOINT),
    )
    for value in variants:
        settings = _settings()
        object.__setattr__(settings, "bybit_fgrid_validate_path", value)
        _assert_boundary_error(
            api,
            "validate_endpoint_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )


def test_grid_modes_feature_flag_and_live_values_are_exact_and_fail_closed():
    api = _api()

    class Number(int):
        pass

    class Text(str):
        pass

    for value in (True, 1.0, "1", Number(1)):
        settings = _settings()
        object.__setattr__(settings, "bybit_fgrid_grid_mode_neutral", value)
        _assert_boundary_error(
            api,
            "validate_grid_mode_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )
    for value in (True, 2.0, "2", Number(2)):
        settings = _settings()
        object.__setattr__(settings, "bybit_fgrid_grid_type_geometric", value)
        _assert_boundary_error(
            api,
            "validate_grid_type_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )
    for value in (True, 1.0, "5000", 4999, Number(5000)):
        settings = _settings()
        object.__setattr__(settings, "bybit_recv_window", value)
        _assert_boundary_error(
            api,
            "validate_recv_window_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )
    for value in (0, 1, "true", None):
        settings = _settings()
        object.__setattr__(settings, "grid_validate_enabled", value)
        _assert_boundary_error(
            api,
            "validate_enabled_flag_invalid",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )
    for field_name, value in (
        ("live_trading_enabled", True),
        ("live_trading_enabled", 0),
        ("allow_live_trading", "YES"),
        ("allow_live_trading", Text("NO")),
    ):
        settings = _settings()
        object.__setattr__(settings, field_name, value)
        _assert_boundary_error(
            api,
            "validate_live_authority_forbidden",
            lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
        )


def test_malicious_environment_configuration_blocks_guard_and_payload_builder(monkeypatch):
    api = _api()
    payload_api = _payload_api()
    with monkeypatch.context() as canonical:
        _clear_policy_environment(canonical)
        canonical.setenv("BYBIT_ENV", "mainnet")
        canonical.setenv("BYBIT_API_BASE_URL", CANONICAL_BASE_URL)
        canonical.setenv("BYBIT_FGRID_VALIDATE_PATH", CANONICAL_ENDPOINT)
        canonical.setenv("BYBIT_FGRID_GRID_MODE_NEUTRAL", "1")
        canonical.setenv("BYBIT_FGRID_GRID_TYPE_GEOMETRIC", "2")
        canonical.setenv("BYBIT_RECV_WINDOW", "5000")
        canonical.setenv("GRID_VALIDATE_ENABLED", "true")
        canonical.setenv("LIVE_TRADING_ENABLED", "false")
        canonical.setenv("ALLOW_LIVE_TRADING", "NO")
        canonical_settings = _config_api().Settings(_env_file=None)
        assert type(canonical_settings.bybit_fgrid_grid_mode_neutral) is int
        assert type(canonical_settings.bybit_fgrid_grid_type_geometric) is int
        assert type(canonical_settings.bybit_recv_window) is int
        assert canonical_settings.bybit_recv_window == 5000
        assert canonical_settings.grid_validate_enabled is True
        assert canonical_settings.live_trading_enabled is False
        assert api.enforce_validate_only_settings(settings=canonical_settings) is None
        assert _build_payload(payload_api)["grid_mode"] == 1
        assert _build_payload(payload_api)["grid_type"] == 2
    variants = (
        ("BYBIT_ENV", "testnet", "validate_environment_forbidden"),
        ("BYBIT_API_BASE_URL", "https://attacker.invalid", "validate_api_base_url_forbidden"),
        ("BYBIT_FGRID_VALIDATE_PATH", "/v5/order/create", "validate_endpoint_forbidden"),
        ("BYBIT_FGRID_GRID_MODE_NEUTRAL", "0", "validate_grid_mode_forbidden"),
        ("BYBIT_FGRID_GRID_TYPE_GEOMETRIC", "1", "validate_grid_type_forbidden"),
        ("BYBIT_RECV_WINDOW", "4999", "validate_recv_window_forbidden"),
        ("LIVE_TRADING_ENABLED", "true", "validate_live_authority_forbidden"),
        ("ALLOW_LIVE_TRADING", "YES", "validate_live_authority_forbidden"),
    )
    for name, value, code in variants:
        with monkeypatch.context() as local:
            _clear_policy_environment(local)
            local.setenv(name, value)
            settings = _config_api().Settings(_env_file=None)
            _assert_boundary_error(
                api,
                code,
                lambda settings=settings: api.enforce_validate_only_settings(settings=settings),
            )
            _assert_boundary_error(api, code, lambda: _build_payload(payload_api))

    raw_aliases = (
        ("BYBIT_FGRID_GRID_MODE_NEUTRAL", "01", "bybit_fgrid_grid_mode_neutral"),
        ("BYBIT_FGRID_GRID_MODE_NEUTRAL", "+1", "bybit_fgrid_grid_mode_neutral"),
        ("BYBIT_FGRID_GRID_MODE_NEUTRAL", "1.0", "bybit_fgrid_grid_mode_neutral"),
        ("BYBIT_FGRID_GRID_TYPE_GEOMETRIC", " 2 ", "bybit_fgrid_grid_type_geometric"),
        ("BYBIT_RECV_WINDOW", "05000", "bybit_recv_window"),
        ("BYBIT_RECV_WINDOW", "5e3", "bybit_recv_window"),
        ("GRID_VALIDATE_ENABLED", "1", "grid_validate_enabled"),
        ("GRID_VALIDATE_ENABLED", "TRUE", "grid_validate_enabled"),
        ("GRID_VALIDATE_ENABLED", "yes", "grid_validate_enabled"),
        ("LIVE_TRADING_ENABLED", "on", "live_trading_enabled"),
        ("LIVE_TRADING_ENABLED", " false ", "live_trading_enabled"),
    )
    for name, value, field_name in raw_aliases:
        with monkeypatch.context() as local:
            _clear_policy_environment(local)
            local.setenv(name, value)
            with pytest.raises(ValidationError) as caught:
                _config_api().Settings(_env_file=None)
            assert any(error["loc"] == (field_name,) for error in caught.value.errors())

    class Text(str):
        pass

    class Number(int):
        pass

    programmatic_aliases = (
        ("bybit_fgrid_grid_mode_neutral", True),
        ("bybit_fgrid_grid_mode_neutral", b"1"),
        ("bybit_fgrid_grid_mode_neutral", Text("1")),
        ("bybit_fgrid_grid_mode_neutral", Number(1)),
        ("bybit_fgrid_grid_type_geometric", "02"),
        ("bybit_recv_window", 5000.0),
        ("bybit_recv_window", Text("5000")),
        ("grid_validate_enabled", 1),
        ("grid_validate_enabled", Text("true")),
        ("live_trading_enabled", 0),
    )
    with monkeypatch.context() as local:
        _clear_policy_environment(local)
        for field_name, value in programmatic_aliases:
            with pytest.raises(ValidationError) as caught:
                _config_api().Settings(_env_file=None, **{field_name: value})
            assert any(error["loc"] == (field_name,) for error in caught.value.errors())

    with monkeypatch.context() as legacy:
        _clear_policy_environment(legacy)
        legacy.setenv("BYBIT_FGRID_CREATE_PATH", "/v5/fgridbot/create")
        legacy.setenv("BYBIT_FGRID_CLOSE_PATH", "/v5/fgridbot/close")
        legacy.setenv("BYBIT_FGRID_DETAIL_PATH", "/v5/fgridbot/detail")
        legacy_settings = _config_api().Settings(_env_file=None)
        assert not hasattr(legacy_settings, "bybit_fgrid_create_path")
        assert not hasattr(legacy_settings, "bybit_fgrid_close_path")
        assert not hasattr(legacy_settings, "bybit_fgrid_detail_path")


def test_private_get_exact_allowlist_and_parameter_schemas_precede_credentials_and_retry(monkeypatch):
    api = _api()

    class Text(str):
        pass

    class Params(dict):
        pass

    accepted = (
        ("/v5/account/info", {}),
        ("/v5/account/wallet-balance", {"accountType": "UNIFIED"}),
        ("/v5/account/fee-rate", {"category": "linear"}),
        (
            "/v5/account/fee-rate",
            {"category": "linear", "symbol": "BTCUSDT"},
        ),
    )
    for endpoint, params in accepted:
        assert api.enforce_private_get_request(endpoint=endpoint, params=params) is None

    endpoint_variants = (
        "/v5/private",
        "/v5/account/wallet-balance/",
        "/v5/account/info?x=1",
        "/v5/account/info#x",
        "https://api.bybit.com/v5/account/info",
        "/v5/order/realtime",
        Text("/v5/account/info"),
        None,
    )
    for endpoint in endpoint_variants:
        _assert_boundary_error(
            api,
            "private_get_endpoint_forbidden",
            lambda endpoint=endpoint: api.enforce_private_get_request(endpoint=endpoint, params={}),
        )
    param_variants = (
        ("/v5/account/info", {"extra": "x"}),
        ("/v5/account/wallet-balance", {}),
        ("/v5/account/wallet-balance", {"accountType": "CONTRACT"}),
        ("/v5/account/fee-rate", {"category": "spot"}),
        ("/v5/account/fee-rate", {"category": "linear", "symbol": "btcusdt"}),
        ("/v5/account/fee-rate", {"category": "linear", "symbol": "BTCUSD"}),
        ("/v5/account/fee-rate", {Text("category"): "linear"}),
        ("/v5/account/fee-rate", {"category": Text("linear")}),
        ("/v5/account/fee-rate", {"category": "linear", "symbol": 1}),
        ("/v5/account/info", Params()),
        ("/v5/account/info", []),
        ("/v5/account/fee-rate", None),
    )
    for endpoint, params in param_variants:
        _assert_boundary_error(
            api,
            "private_get_params_forbidden",
            lambda endpoint=endpoint, params=params: api.enforce_private_get_request(
                endpoint=endpoint, params=params
            ),
        )

    success_events: list[str] = []
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: success_events.append("credentials"),
    )
    success_client = _client(_settings(), success_events)
    response = success_client.private_get("/v5/account/info")
    assert response["retCode"] == 0
    assert success_events == ["credentials", "rate_limit", "http"]
    assert success_client.private_http.calls[0][0] == "/v5/account/info"
    assert success_client.private_http.calls[0][1] is None

    events: list[str] = []
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    client = _client(
        _settings(
            bybit_env="testnet",
            bybit_api_key="",
            bybit_api_secret="",
        ),
        events,
    )
    client._private_get = lambda prepared: events.append("retry_helper")
    _assert_boundary_error(
        api,
        "private_get_endpoint_forbidden",
        lambda: client.private_get("/v5/order/realtime", {}),
    )
    assert events == []
    for params in ({"extra": "x"}, Params()):
        _assert_boundary_error(
            api,
            "private_get_params_forbidden",
            lambda params=params: client.private_get("/v5/account/info", params),
        )
        assert events == []


def test_private_get_retry_snapshots_query_credentials_and_policy(monkeypatch):
    api = _api()
    client_api = _client_api()
    events: list[str] = []
    sign_calls: list[tuple[str, str]] = []
    settings = _settings(
        bybit_api_key="initial-key",
        bybit_api_secret="initial-secret",
        bybit_recv_window=5000,
    )
    params = {"symbol": "BTCUSDT", "category": "linear"}

    def mutate_sources():
        params.clear()
        params.update({"category": "spot", "symbol": "ETHUSDT"})
        object.__setattr__(settings, "bybit_api_key", "mutated-key")
        object.__setattr__(settings, "bybit_api_secret", "mutated-secret")
        object.__setattr__(settings, "bybit_recv_window", 1)
        object.__setattr__(settings, "bybit_api_base_url", "https://attacker.invalid")

    http = _FailingGetHttp(events, on_first=mutate_sources)
    client = _client(settings, events, http=http)
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    monkeypatch.setattr(
        client_api,
        "sign_v5",
        lambda secret, target: sign_calls.append((secret, target)) or "snapshot-signature",
    )
    monkeypatch.setattr(client_api.BybitClient._private_get.retry, "sleep", lambda delay: None)
    with pytest.raises(httpx.ConnectError):
        client.private_get("/v5/account/fee-rate", params)

    exact_query = "category=linear&symbol=BTCUSDT"
    assert tuple(call[0] for call in http.calls) == (
        f"/v5/account/fee-rate?{exact_query}",
    ) * 4
    assert all(call[1] is None for call in http.calls)
    assert all(call[2]["X-BAPI-API-KEY"] == "initial-key" for call in http.calls)
    assert all(call[2]["X-BAPI-RECV-WINDOW"] == "5000" for call in http.calls)
    assert len(sign_calls) == 4
    assert all(secret == "initial-secret" for secret, target in sign_calls)
    assert all(target.endswith(exact_query) for secret, target in sign_calls)
    assert events.count("credentials") == 1
    assert events.count("rate_limit") == 4
    assert events.count("http") == 4
    assert api.CANONICAL_PRIVATE_GET_ENDPOINTS == PRIVATE_GET_ENDPOINTS


def test_payload_guard_requires_exact_dict_keys_neutral_and_geometric_values():
    api = _api()
    payload = _payload()
    assert set(payload) == EXPECTED_PAYLOAD_KEYS
    assert api.enforce_validate_only_payload(payload=payload) is None

    class Payload(dict):
        pass

    class Text(str):
        pass

    class Number(int):
        pass

    for value in (None, object(), Payload(payload)):
        _assert_boundary_error(
            api,
            "validate_payload_not_exact_dict",
            lambda value=value: api.enforce_validate_only_payload(payload=value),
        )
    missing = _payload()
    missing.pop("grid_type")
    extra = {**_payload(), "side": "Buy"}
    subclass_key = _payload()
    subclass_key[Text("symbol")] = subclass_key.pop("symbol")
    for value in (missing, extra, subclass_key):
        _assert_boundary_error(
            api,
            "validate_payload_keys_invalid",
            lambda value=value: api.enforce_validate_only_payload(payload=value),
        )
    take_profit = {**_payload(), "take_profit_price": "80000"}
    _assert_boundary_error(
        api,
        "validate_payload_keys_invalid",
        lambda: api.enforce_validate_only_payload(payload=take_profit),
    )
    for value in (True, 1.0, "1", Number(1)):
        candidate = {**_payload(), "grid_mode": value}
        _assert_boundary_error(
            api,
            "validate_payload_grid_mode_forbidden",
            lambda candidate=candidate: api.enforce_validate_only_payload(payload=candidate),
        )
    for value in (True, 2.0, "2", Number(2)):
        candidate = {**_payload(), "grid_type": value}
        _assert_boundary_error(
            api,
            "validate_payload_grid_type_forbidden",
            lambda candidate=candidate: api.enforce_validate_only_payload(payload=candidate),
        )
    for value in ("btcusdt", "BTC- USDT", "BTCUSD", Text("BTCUSDT")):
        candidate = {**_payload(), "symbol": value}
        _assert_boundary_error(
            api,
            "validate_payload_symbol_forbidden",
            lambda candidate=candidate: api.enforce_validate_only_payload(payload=candidate),
        )
    for field_name, value in (
        ("leverage", "01"),
        ("leverage", "1.0"),
        ("min_price", 58500),
        ("max_price", "7.15e4"),
        ("init_margin", "100.00"),
        ("stop_loss_price", "-1"),
    ):
        candidate = {**_payload(), field_name: value}
        _assert_boundary_error(
            api,
            "validate_payload_decimal_forbidden",
            lambda candidate=candidate: api.enforce_validate_only_payload(payload=candidate),
        )
    for value in (True, 1, 101, "10"):
        candidate = {**_payload(), "cell_number": value}
        _assert_boundary_error(
            api,
            "validate_payload_cell_number_forbidden",
            lambda candidate=candidate: api.enforce_validate_only_payload(payload=candidate),
        )
    for stop_loss, minimum, maximum in (
        ("58500", "58500", "71500"),
        ("60000", "58500", "71500"),
        ("55250", "71500", "58500"),
    ):
        candidate = {
            **_payload(),
            "stop_loss_price": stop_loss,
            "min_price": minimum,
            "max_price": maximum,
        }
        _assert_boundary_error(
            api,
            "validate_payload_geometry_forbidden",
            lambda candidate=candidate: api.enforce_validate_only_payload(payload=candidate),
        )


def test_payload_builder_has_no_mode_override_and_emits_exact_fixed_atoms(monkeypatch):
    api = _api()
    payload_api = _payload_api()
    _clear_policy_environment(monkeypatch)
    signature = inspect.signature(payload_api.build_fgrid_validate_payload)
    assert "grid_mode" not in signature.parameters
    assert "grid_type" not in signature.parameters
    built = _build_payload(payload_api)
    assert set(built) == EXPECTED_PAYLOAD_KEYS
    assert type(built["grid_mode"]) is int
    assert built["grid_mode"] == api.CANONICAL_FGRID_GRID_MODE_NEUTRAL == 1
    assert type(built["grid_type"]) is int
    assert built["grid_type"] == api.CANONICAL_FGRID_GRID_TYPE_GEOMETRIC == 2
    with pytest.raises(TypeError):
        payload_api.build_fgrid_validate_payload(
            "BTCUSDT", Decimal("65000"), Decimal("0.1"), grid_mode=1
        )
    with pytest.raises(TypeError):
        payload_api.build_fgrid_validate_payload(
            "BTCUSDT", Decimal("65000"), Decimal("0.1"), grid_type=2
        )


def test_client_signatures_remove_endpoint_and_live_authority_from_validate_path():
    api = _api()
    client_api = _client_api()
    client_type = client_api.BybitClient
    assert tuple(inspect.signature(client_type.validate_grid_bot).parameters) == (
        "self",
        "payload",
    )
    assert tuple(inspect.signature(client_type._private_validate_post).parameters) == (
        "self",
        "prepared",
    )
    assert tuple(inspect.signature(client_type._private_get).parameters) == (
        "self",
        "prepared",
    )
    assert tuple(inspect.signature(client_type.private_post).parameters) == (
        "self",
        "endpoint",
        "body",
    )
    assert not hasattr(client_type.private_post, "retry")
    assert not hasattr(client_type.private_get, "retry")
    assert hasattr(client_type._private_validate_post, "retry")
    assert hasattr(client_type._private_get, "retry")

    tree = ast.parse(inspect.getsource(client_api))
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    posts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "post"
    ]
    assert len(posts) == 1
    owner = parents[posts[0]]
    while not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
        owner = parents[owner]
    assert owner.name == "_private_validate_post"
    assert posts[0].args
    assert isinstance(posts[0].args[0], ast.Name)
    assert posts[0].args[0].id == "CANONICAL_FGRID_VALIDATE_ENDPOINT"

    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    generic = functions["private_post"]
    assert generic.decorator_list == []
    body = _meaningful_body(generic)
    assert len(body) == 1
    assert isinstance(body[0], ast.Raise)
    assert isinstance(body[0].exc, ast.Call)
    assert isinstance(body[0].exc.func, ast.Name)
    assert body[0].exc.func.id == "ValidateOnlyBoundaryError"
    assert len(body[0].exc.args) == 1
    assert isinstance(body[0].exc.args[0], ast.Constant)
    assert body[0].exc.args[0].value == "generic_private_post_forbidden"
    validate_calls = [
        node.func.attr
        for node in ast.walk(functions["validate_grid_bot"])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "private_post" not in validate_calls
    assert "_private_validate_post" in validate_calls
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_invalid_generic_settings_and_payload_calls_have_zero_pretransport_events(monkeypatch):
    api = _api()
    events: list[str] = []
    config_api = _config_api()
    monkeypatch.setattr(
        config_api.Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    client = _client(_settings(), events)
    client._private_headers = lambda body: events.append("signing") or {}
    client._private_validate_post = lambda body: events.append("retry_helper")

    class Text(str):
        pass

    for endpoint in (
        CANONICAL_ENDPOINT,
        "/v5/fgridbot/create",
        "/v5/order/create",
        "/v5/asset/withdraw/create",
        "https://api.bybit.com/v5/fgridbot/validate",
        f"{CANONICAL_ENDPOINT}?x=1",
        Text(CANONICAL_ENDPOINT),
        None,
    ):
        _assert_boundary_error(
            api,
            "generic_private_post_forbidden",
            lambda endpoint=endpoint: client.private_post(endpoint, _payload()),
        )
        assert events == []

    invalid_settings = _settings(bybit_fgrid_validate_path="/v5/fgridbot/create")
    client.settings = invalid_settings
    _assert_boundary_error(
        api,
        "validate_endpoint_forbidden",
        lambda: client.validate_grid_bot(_payload()),
    )
    assert events == []

    client.settings = _settings()
    invalid_payload = {**_payload(), "grid_mode": 0}
    _assert_boundary_error(
        api,
        "validate_payload_grid_mode_forbidden",
        lambda: client.validate_grid_bot(invalid_payload),
    )
    assert events == []


def test_valid_disabled_feature_returns_before_credentials_signing_rate_limit_and_http(monkeypatch):
    api = _api()
    events: list[str] = []
    settings = _settings(
        grid_validate_enabled=False,
        bybit_api_key="",
        bybit_api_secret="",
    )
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    client = _client(settings, events)
    client._private_headers = lambda body: events.append("signing") or {}
    client._private_validate_post = lambda body: events.append("retry_helper")
    invalid_payload = {**_payload(), "grid_type": 1}
    _assert_boundary_error(
        api,
        "validate_payload_grid_type_forbidden",
        lambda: client.validate_grid_bot(invalid_payload),
    )
    assert events == []
    assert client.validate_grid_bot(_payload()) == {
        "skipped": True,
        "reason": "GRID_VALIDATE_ENABLED is false",
    }
    assert events == []
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_canonical_validate_orders_credentials_signing_rate_limit_and_single_http(monkeypatch):
    api = _api()
    client_api = _client_api()
    events: list[str] = []
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    client = _client(_settings(), events)
    monkeypatch.setattr(
        client_api,
        "sign_v5",
        lambda secret, target: events.append("signing") or "snapshot-signature",
    )
    result = client.validate_grid_bot(_payload())
    assert result["retCode"] == 0
    assert events == ["credentials", "signing", "rate_limit", "http"]
    assert len(client.private_http.calls) == 1
    endpoint, content, headers = client.private_http.calls[0]
    assert type(endpoint) is str
    assert endpoint == api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT
    assert json.loads(content) == _payload()
    assert headers["X-BAPI-API-KEY"] == "test-key-not-a-secret"
    assert headers["Content-Type"] == "application/json"
    assert client.stats.api_calls_attempted == 1
    assert client.stats.api_calls_succeeded == 1
    assert client.stats.api_calls_failed == 0


def test_retryable_transport_repeats_only_the_same_canonical_validate_endpoint(monkeypatch):
    api = _api()
    client_api = _client_api()
    events: list[str] = []
    sign_calls: list[tuple[str, str]] = []
    settings = _settings(
        bybit_api_key="initial-key",
        bybit_api_secret="initial-secret",
        bybit_recv_window=5000,
    )
    payload = _payload()

    def mutate_sources():
        payload["grid_mode"] = 0
        payload["grid_type"] = 1
        payload["stop_loss_price"] = "70000"
        object.__setattr__(settings, "bybit_api_key", "mutated-key")
        object.__setattr__(settings, "bybit_api_secret", "mutated-secret")
        object.__setattr__(settings, "bybit_recv_window", 1)
        object.__setattr__(settings, "bybit_api_base_url", "https://attacker.invalid")

    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    monkeypatch.setattr(
        client_api,
        "sign_v5",
        lambda secret, target: sign_calls.append((secret, target)) or "snapshot-signature",
    )
    failing_http = _FailingHttp(events, on_first=mutate_sources)
    client = _client(settings, events, http=failing_http)
    retry_controller = client_api.BybitClient._private_validate_post.retry
    monkeypatch.setattr(retry_controller, "sleep", lambda delay: None)
    with pytest.raises(httpx.ConnectError):
        client.validate_grid_bot(payload)
    endpoints = tuple(call[0] for call in failing_http.calls)
    assert endpoints == (CANONICAL_ENDPOINT,) * 4
    assert all(type(endpoint) is str for endpoint in endpoints)
    assert all(endpoint == api.CANONICAL_FGRID_VALIDATE_ENDPOINT for endpoint in endpoints)
    expected_body = json.dumps(_payload(), separators=(",", ":"), ensure_ascii=False)
    assert all(call[1] == expected_body for call in failing_http.calls)
    assert all(call[2]["X-BAPI-API-KEY"] == "initial-key" for call in failing_http.calls)
    assert all(call[2]["X-BAPI-RECV-WINDOW"] == "5000" for call in failing_http.calls)
    assert len(sign_calls) == 4
    assert all(secret == "initial-secret" for secret, target in sign_calls)
    assert all(target.endswith(expected_body) for secret, target in sign_calls)
    assert events.count("credentials") == 1
    assert events.count("rate_limit") == 4
    assert events.count("http") == 4


def test_prepared_helpers_reject_foreign_values_and_actual_origin_drift_before_signing(monkeypatch):
    api = _api()
    events: list[str] = []
    client_api = _client_api()
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: events.append("credentials"),
    )
    monkeypatch.setattr(
        client_api,
        "sign_v5",
        lambda secret, target: events.append("signing") or "signature",
    )

    capture_client = _client(_settings(), events)
    captured = []
    capture_client._private_validate_post = (
        lambda prepared: captured.append(prepared) or {"captured": True}
    )
    assert capture_client.validate_grid_bot(_payload()) == {"captured": True}
    assert len(captured) == 1
    prepared = captured[0]
    assert is_dataclass(prepared)
    assert not hasattr(prepared, "__dict__")
    hash(prepared)
    first_field = fields(prepared)[0].name
    with pytest.raises(FrozenInstanceError):
        setattr(prepared, first_field, getattr(prepared, first_field))
    forged = object.__new__(type(prepared))
    complete_forgery = object.__new__(type(prepared))
    for field in fields(prepared):
        object.__setattr__(
            complete_forgery,
            field.name,
            getattr(prepared, field.name),
        )
    events.clear()

    client = _client(_settings(), events)
    for value in (object(), {}, forged, complete_forgery):
        _assert_boundary_error(
            api,
            "validate_prepared_request_invalid",
            lambda value=value: client._private_validate_post(value),
        )
    assert events == []

    get_capture = []
    capture_client._private_get = lambda prepared: get_capture.append(prepared) or {"captured": True}
    assert capture_client.private_get("/v5/account/info") == {"captured": True}
    assert len(get_capture) == 1
    get_prepared = get_capture[0]
    assert is_dataclass(get_prepared)
    assert not hasattr(get_prepared, "__dict__")
    hash(get_prepared)
    complete_get_forgery = object.__new__(type(get_prepared))
    for field in fields(get_prepared):
        object.__setattr__(
            complete_get_forgery,
            field.name,
            getattr(get_prepared, field.name),
        )
    events.clear()
    for value in (object(), {}, complete_get_forgery):
        _assert_boundary_error(
            api,
            "private_get_prepared_request_invalid",
            lambda value=value: client._private_get(value),
        )
    assert events == []

    client.private_http.base_url = httpx.URL("https://attacker.invalid")
    _assert_boundary_error(
        api,
        "private_http_origin_forbidden",
        lambda: client.validate_grid_bot(_payload()),
    )
    assert events == []

    events.clear()
    drifting_http = _FailingHttp(events)
    drifting_http.on_first = lambda: setattr(
        drifting_http, "base_url", httpx.URL("https://attacker.invalid")
    )
    client = _client(_settings(), events, http=drifting_http)
    monkeypatch.setattr(client_api.BybitClient._private_validate_post.retry, "sleep", lambda delay: None)
    _assert_boundary_error(
        api,
        "private_http_origin_forbidden",
        lambda: client.validate_grid_bot(_payload()),
    )
    assert events == ["credentials", "signing", "rate_limit", "http"]
    assert len(drifting_http.calls) == 1

    events.clear()
    client = _client(_settings(), events)
    client.private_http.base_url = httpx.URL("https://attacker.invalid")
    _assert_boundary_error(
        api,
        "private_http_origin_forbidden",
        lambda: client.private_get("/v5/account/info"),
    )
    assert events == []

    events.clear()
    drifting_get_http = _FailingGetHttp(events)
    drifting_get_http.on_first = lambda: setattr(
        drifting_get_http, "base_url", httpx.URL("https://attacker.invalid")
    )
    client = _client(_settings(), events, http=drifting_get_http)
    monkeypatch.setattr(client_api.BybitClient._private_get.retry, "sleep", lambda delay: None)
    _assert_boundary_error(
        api,
        "private_http_origin_forbidden",
        lambda: client.private_get("/v5/account/info"),
    )
    assert events == ["credentials", "signing", "rate_limit", "http"]
    assert len(drifting_get_http.calls) == 1


def test_public_policy_rebinding_does_not_weaken_captured_client_or_builder_guards(monkeypatch):
    api = _api()
    client_api = _client_api()
    payload_api = _payload_api()
    events: list[str] = []
    monkeypatch.setattr(api, "enforce_validate_only_settings", lambda **kwargs: None)
    monkeypatch.setattr(api, "enforce_private_get_request", lambda **kwargs: None)
    monkeypatch.setattr(api, "enforce_validate_only_payload", lambda **kwargs: None)
    monkeypatch.setattr(api, "CANONICAL_BYBIT_ENV", "testnet")
    monkeypatch.setattr(api, "CANONICAL_BYBIT_API_BASE_URL", "https://attacker.invalid")
    monkeypatch.setattr(api, "CANONICAL_FGRID_VALIDATE_ENDPOINT", "/v5/order/create")
    monkeypatch.setattr(api, "CANONICAL_PRIVATE_GET_ENDPOINTS", ("/v5/order/realtime",))
    monkeypatch.setattr(api, "CANONICAL_FGRID_GRID_MODE_NEUTRAL", 0)
    monkeypatch.setattr(api, "CANONICAL_FGRID_GRID_TYPE_GEOMETRIC", 1)

    client = _client(
        _settings(bybit_fgrid_validate_path="/v5/asset/withdraw/create"),
        events,
    )
    client._private_validate_post = lambda body: events.append("retry_helper")
    _assert_boundary_error(
        api,
        "validate_endpoint_forbidden",
        lambda: client.validate_grid_bot(_payload()),
    )
    assert events == []

    for settings, code in (
        (_settings(bybit_env="testnet"), "validate_environment_forbidden"),
        (
            _settings(bybit_api_base_url="https://attacker.invalid"),
            "validate_api_base_url_forbidden",
        ),
    ):
        client = _client(settings, events)
        client._private_validate_post = lambda prepared: events.append("retry_helper")
        _assert_boundary_error(
            api,
            code,
            lambda client=client: client.validate_grid_bot(_payload()),
        )
        assert events == []

    client = _client(_settings(), events)
    client._private_get = lambda prepared: events.append("retry_helper")
    _assert_boundary_error(
        api,
        "private_get_endpoint_forbidden",
        lambda: client.private_get("/v5/order/realtime", {}),
    )
    assert events == []
    invalid_payload = {**_payload(), "grid_mode": 0}
    client._private_validate_post = lambda prepared: events.append("retry_helper")
    _assert_boundary_error(
        api,
        "validate_payload_grid_mode_forbidden",
        lambda: client.validate_grid_bot(invalid_payload),
    )
    assert events == []

    poisoned_settings = _settings()
    object.__setattr__(poisoned_settings, "bybit_fgrid_grid_type_geometric", 1)
    monkeypatch.setattr(payload_api, "load_settings", lambda: poisoned_settings)
    _assert_boundary_error(
        api,
        "validate_grid_type_forbidden",
        lambda: _build_payload(payload_api),
    )
    monkeypatch.setattr(payload_api, "load_settings", lambda: _settings())
    built = _build_payload(payload_api)
    assert built["grid_mode"] == 1
    assert built["grid_type"] == 2
    assert client_api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_create_close_are_immediate_unconditional_stubs_and_mutation_methods_absent():
    api = _api()
    client_api = _client_api()
    client = object.__new__(client_api.BybitClient)

    class Bomb:
        def __getattribute__(self, name):
            raise AssertionError(f"pre-raise side effect: {name}")

    client.settings = Bomb()
    for name in ("create_grid_bot", "close_grid_bot"):
        with pytest.raises(NotImplementedError):
            getattr(client, name)(runtime_live=True, payload=_payload())

    tree = ast.parse(inspect.getsource(client_api))
    functions = {
        node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    for name in ("create_grid_bot", "close_grid_bot"):
        node = functions[name]
        assert node.decorator_list == []
        body = _meaningful_body(node)
        assert len(body) == 1
        assert _is_direct_not_implemented_raise(body[0])

    forbidden_methods = (
        "create_order",
        "place_order",
        "amend_order",
        "cancel_order",
        "withdraw",
        "withdraw_funds",
        "transfer_funds",
        "mutate_wallet",
        "mutate_position",
        "execute_live",
    )
    assert all(not hasattr(client_api.BybitClient, name) for name in forbidden_methods)
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_source_audit_rejects_direct_dynamic_generic_and_external_http_post(tmp_path):
    api = _api()
    audit_api = _audit_api()
    root = tmp_path / "generic-calls"
    _write_source(
        root,
        "scripts/evil.py",
        """
        def direct(client, endpoint, body):
            return client.private_post(endpoint, body)

        def dynamic(client, endpoint, body):
            return getattr(client, "private_post")(endpoint, body)

        def raw_http(client, endpoint, body):
            return client.http.post(endpoint, json=body)

        def raw_private_http(client, endpoint, body):
            return client.private_http.post(endpoint, json=body)
        """,
    )
    result = audit_api.audit_source_tree(root)
    joined = "\n".join(result.violations)
    assert result.ok is False
    assert "generic private_post call is forbidden" in joined
    assert "dynamic lookup of private_post is forbidden" in joined
    assert "HTTP POST outside canonical client transport is forbidden" in joined
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_source_audit_rejects_dynamic_or_variant_transport_and_misleading_stubs(tmp_path):
    api = _api()
    audit_api = _audit_api()
    dynamic_root = tmp_path / "dynamic-client"
    _write_source(
        dynamic_root,
        "src/bybit_grid/bybit/client.py",
        """
        class BybitClient:
            def _private_validate_post(self, endpoint, body):
                return self.private_http.post(endpoint, json=body)

            def create_grid_bot(self):
                mutate()
                def decoy():
                    raise NotImplementedError("nested")

            def close_grid_bot(self):
                if False:
                    raise NotImplementedError("unreachable")
                mutate()
        """,
    )
    dynamic = audit_api.audit_source_tree(dynamic_root)
    dynamic_joined = "\n".join(dynamic.violations)
    assert dynamic.ok is False
    assert "canonical validate transport shape is required" in dynamic_joined
    assert "create_grid_bot must be immediate unconditional NotImplementedError stub" in dynamic_joined
    assert "close_grid_bot must be immediate unconditional NotImplementedError stub" in dynamic_joined

    variant_root = tmp_path / "variant-client"
    _write_source(
        variant_root,
        "src/bybit_grid/bybit/client.py",
        """
        class BybitClient:
            def _private_validate_post(self, body):
                return self.private_http.post(
                    "https://api.bybit.com/v5/fgridbot/validate?category=linear",
                    json=body,
                )

            def create_grid_bot(self):
                raise NotImplementedError("forbidden")

            def close_grid_bot(self):
                raise NotImplementedError("forbidden")
        """,
    )
    variant = audit_api.audit_source_tree(variant_root)
    variant_joined = "\n".join(variant.violations)
    assert variant.ok is False
    assert "canonical validate transport shape is required" in variant_joined

    universe_root = tmp_path / "universe-preflight"
    _write_source(
        universe_root,
        "scripts/validate_universe_fgrid_constraints.py",
        """
        def main(settings):
            settings.require_private_credentials()
            pool = ThreadPoolExecutor(max_workers=10)
            enforce_validate_only_settings(settings=settings)
            return pool

        def _validate_symbol(row):
            settings = load_settings()
            return BybitClient(settings)
        """,
    )
    universe = audit_api.audit_source_tree(universe_root)
    universe_joined = "\n".join(universe.violations)
    assert universe.ok is False
    assert "validate universe policy preflight must precede credentials and threads" in universe_joined
    assert "validate universe workers must use preflighted settings" in universe_joined

    for directory_name, worker_source in (
        (
            "worker-settings-constructor",
            """
            def _validate_symbol(row):
                settings = Settings()
                return BybitClient(settings)
            """,
        ),
        (
            "worker-environment-read",
            """
            def _validate_symbol(row, settings):
                value = os.environ["BYBIT_API_BASE_URL"]
                return BybitClient(settings), value
            """,
        ),
        (
            "worker-indirect-payload-settings-reload",
            """
            def _build_candidates(row):
                return build_min_sweep_candidates(row)

            def _validate_symbol(row, settings):
                candidates = _build_candidates(row)
                return BybitClient(settings), candidates
            """,
        ),
    ):
        worker_root = tmp_path / directory_name
        _write_source(
            worker_root,
            "scripts/validate_universe_fgrid_constraints.py",
            worker_source,
        )
        worker_result = audit_api.audit_source_tree(worker_root)
        assert worker_result.ok is False
        assert "validate universe workers must use preflighted settings" in "\n".join(
            worker_result.violations
        )

    swallowed_root = tmp_path / "swallowed-boundary"
    _write_source(
        swallowed_root,
        "scripts/validate_sample_grid.py",
        """
        def main(client, payload):
            try:
                return client.validate_grid_bot(payload)
            except Exception:
                return {"status": "swallowed"}
        """,
    )
    _write_source(
        swallowed_root,
        "scripts/validate_universe_fgrid_constraints.py",
        """
        def _validate_symbol(client, payload):
            try:
                return client.validate_grid_bot(payload)
            except Exception:
                return {"status": "swallowed"}
        """,
    )
    swallowed_result = audit_api.audit_source_tree(swallowed_root)
    assert swallowed_result.ok is False
    swallowed_joined = "\n".join(swallowed_result.violations)
    assert swallowed_joined.count(
        "validate-only boundary error must be re-raised before broad handler"
    ) >= 2

    late_sample_root = tmp_path / "late-sample-preflight"
    _write_source(
        late_sample_root,
        "scripts/validate_sample_grid.py",
        """
        def main():
            settings = load_settings()
            reason = _refusal_reason(settings)
            client = BybitClient(settings)
            enforce_validate_only_settings(settings=settings)
            return client, reason
        """,
    )
    late_sample_result = audit_api.audit_source_tree(late_sample_root)
    assert late_sample_result.ok is False
    assert "validate sample policy preflight must precede side effects" in "\n".join(
        late_sample_result.violations
    )

    real_root = Path(audit_api.__file__).resolve().parents[3]
    real_result = audit_api.audit_source_tree(real_root)
    assert real_result.ok, "\n".join(real_result.violations)

    sample_tree = ast.parse(
        (real_root / "scripts/validate_sample_grid.py").read_text(encoding="utf-8")
    )
    sample_call_attributes = {
        node.func.attr
        for node in ast.walk(sample_tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "validate_grid_bot" in sample_call_attributes
    assert "private_post" not in sample_call_attributes
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "bybit_fgrid_validate_path"
        for node in ast.walk(sample_tree)
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "bybit_grid.bybit.validate_only"
        and any(alias.name == "CANONICAL_FGRID_VALIDATE_ENDPOINT" for alias in node.names)
        for node in sample_tree.body
    )
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "bybit_grid.bybit.validate_only"
        and {"ValidateOnlyBoundaryError", "enforce_validate_only_settings"}
        <= {alias.name for alias in node.names}
        for node in sample_tree.body
    )
    sample_functions = {
        node.name: node
        for node in sample_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    sample_main = sample_functions["main"]
    sample_main_calls = [node for node in ast.walk(sample_main) if isinstance(node, ast.Call)]
    sample_preflights = [
        call
        for call in sample_main_calls
        if isinstance(call.func, ast.Name) and call.func.id == "enforce_validate_only_settings"
    ]
    assert len(sample_preflights) == 1
    preflight_line = sample_preflights[0].lineno
    for call in sample_main_calls:
        called_name = None
        if isinstance(call.func, ast.Name):
            called_name = call.func.id
        elif isinstance(call.func, ast.Attribute):
            called_name = call.func.attr
        if called_name in {
            "_refusal_reason",
            "_market_numbers",
            "_write_json",
            "build_fgrid_validate_payload",
            "BybitClient",
            "read_text",
            "static_payload",
            "utc_now_iso",
            "write_sprint_report",
        }:
            assert preflight_line < call.lineno
    _assert_boundary_reraised_before_broad(sample_main)

    universe_tree = ast.parse(
        (real_root / "scripts/validate_universe_fgrid_constraints.py").read_text(
            encoding="utf-8"
        )
    )
    universe_functions = {
        node.name: node
        for node in universe_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    worker = universe_functions["_validate_symbol"]
    worker_parameters = {argument.arg for argument in worker.args.args}
    worker_calls = [node for node in ast.walk(worker) if isinstance(node, ast.Call)]
    assert not any(isinstance(call.func, ast.Name) and call.func.id == "load_settings" for call in worker_calls)
    assert not any(isinstance(call.func, ast.Name) and call.func.id == "Settings" for call in worker_calls)
    assert not any(
        isinstance(call.func, ast.Name)
        and call.func.id in {"build_min_sweep_candidates", "build_fgrid_validate_payload"}
        for call in worker_calls
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}
        for node in ast.walk(worker)
    )
    bybit_client_calls = [
        call
        for call in worker_calls
        if isinstance(call.func, ast.Name) and call.func.id == "BybitClient"
    ]
    assert bybit_client_calls
    assert any(
        call.args
        and isinstance(call.args[0], ast.Name)
        and call.args[0].id in worker_parameters
        for call in bybit_client_calls
    )
    _assert_boundary_reraised_before_broad(worker)

    ordinary_path = real_root / "tests/test_sprint_01_5_hotfix.py"
    ordinary_source = ordinary_path.read_text(encoding="utf-8")
    ordinary_tree = ast.parse(ordinary_source)
    ordinary_tests = {
        node.name: node for node in ordinary_tree.body if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
    }
    assert len(ordinary_tests) >= 6
    assert {
        "test_private_get_signs_same_query_string_sent",
        "test_mark_price_kline_5_fields_nullable_volume_turnover",
        "test_quality_boundary_duplicate_and_bad_ohlc",
        "test_redaction_covers_headers_and_raw_strings",
    } <= set(ordinary_tests)
    assert "https://example.test" not in ordinary_source
    assert '"/v5/private"' not in ordinary_source
    ordinary_calls = [node for node in ast.walk(ordinary_tree) if isinstance(node, ast.Call)]
    ordinary_call_attributes = {
        call.func.attr for call in ordinary_calls if isinstance(call.func, ast.Attribute)
    }
    assert {"private_get", "private_post", "validate_grid_bot"} <= ordinary_call_attributes
    ordinary_strings = {
        node.value
        for node in ast.walk(ordinary_tree)
        if isinstance(node, ast.Constant) and type(node.value) is str
    }
    assert EXPECTED_PAYLOAD_KEYS <= ordinary_strings
    assert not any(
        isinstance(call.func, ast.Attribute)
        and call.func.attr in {"skip", "xfail", "importorskip"}
        for call in ordinary_calls
    )
    for handler in (node for node in ast.walk(ordinary_tree) if isinstance(node, ast.ExceptHandler)):
        assert not isinstance(handler.type, ast.Name) or handler.type.id not in {
            "Exception",
            "BaseException",
        }
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_signed_get_and_validate_recheck_origin_after_rate_limit_before_http(monkeypatch):
    api = _api()
    client_api = _client_api()
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: None,
    )
    monkeypatch.setattr(client_api, "sign_v5", lambda secret, target: "signature")

    get_events: list[str] = []
    get_http = _Http(get_events)
    get_client = _client(_settings(), get_events, http=get_http)
    get_client.rate_limiter = _OriginDriftLimiter(get_events, get_http)
    _assert_boundary_error(
        api,
        "private_http_origin_forbidden",
        lambda: get_client.private_get("/v5/account/info"),
    )
    assert get_events == ["rate_limit"]
    assert get_http.calls == []

    post_events: list[str] = []
    post_http = _Http(post_events)
    post_client = _client(_settings(), post_events, http=post_http)
    post_client.rate_limiter = _OriginDriftLimiter(post_events, post_http)
    _assert_boundary_error(
        api,
        "private_http_origin_forbidden",
        lambda: post_client.validate_grid_bot(_payload()),
    )
    assert post_events == ["rate_limit"]
    assert post_http.calls == []


def test_prepared_capabilities_are_client_bound_single_use_and_retry_scoped(monkeypatch):
    api = _api()
    client_api = _client_api()
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: None,
    )
    monkeypatch.setattr(client_api, "sign_v5", lambda secret, target: "signature")
    monkeypatch.setattr(client_api.BybitClient._private_get.retry, "sleep", lambda delay: None)
    monkeypatch.setattr(
        client_api.BybitClient._private_validate_post.retry,
        "sleep",
        lambda delay: None,
    )

    get_events: list[str] = []
    get_http = _RetryOnceHttp(get_events)
    get_owner = _client(_settings(), get_events, http=get_http)
    get_foreign = _client(_settings(), [])
    original_get = get_owner._private_get
    captured_get: list[object] = []

    def get_with_cross_client_probe(prepared):
        captured_get.append(prepared)
        _assert_boundary_error(
            api,
            "private_get_prepared_request_invalid",
            lambda: client_api.BybitClient._private_get.__wrapped__(get_foreign, prepared),
        )
        return original_get(prepared)

    get_owner._private_get = get_with_cross_client_probe
    assert get_owner.private_get("/v5/account/info")["retCode"] == 0
    assert len(get_http.calls) == 2
    assert len(captured_get) == 1
    _assert_boundary_error(
        api,
        "private_get_prepared_request_invalid",
        lambda: client_api.BybitClient._private_get.__wrapped__(
            get_owner,
            captured_get[0],
        ),
    )
    assert len(get_http.calls) == 2

    post_events: list[str] = []
    post_http = _RetryOnceHttp(post_events)
    post_owner = _client(_settings(), post_events, http=post_http)
    post_foreign = _client(_settings(), [])
    original_post = post_owner._private_validate_post
    captured_post: list[object] = []

    def post_with_cross_client_probe(prepared):
        captured_post.append(prepared)
        _assert_boundary_error(
            api,
            "validate_prepared_request_invalid",
            lambda: client_api.BybitClient._private_validate_post.__wrapped__(
                post_foreign,
                prepared,
            ),
        )
        return original_post(prepared)

    post_owner._private_validate_post = post_with_cross_client_probe
    assert post_owner.validate_grid_bot(_payload())["retCode"] == 0
    assert len(post_http.calls) == 2
    assert len(captured_post) == 1
    _assert_boundary_error(
        api,
        "validate_prepared_request_invalid",
        lambda: client_api.BybitClient._private_validate_post.__wrapped__(
            post_owner,
            captured_post[0],
        ),
    )
    assert len(post_http.calls) == 2


def test_prepared_capability_repr_never_exposes_snapshot_credentials():
    api = _api()
    secret_key = "repr-key-7f0de915"
    secret_value = "repr-secret-94f2c301"
    settings = _settings(bybit_api_key=secret_key, bybit_api_secret=secret_value)
    client = _client(settings, [])
    prepared_values: list[object] = []
    client._private_get = lambda prepared: prepared_values.append(prepared) or {"retCode": 0}
    client._private_validate_post = (
        lambda prepared: prepared_values.append(prepared) or {"retCode": 0}
    )

    assert client.private_get("/v5/account/info")["retCode"] == 0
    assert client.validate_grid_bot(_payload())["retCode"] == 0
    assert len(prepared_values) == 2
    for prepared in prepared_values:
        credential_fields = {
            getattr(prepared, field.name): field
            for field in fields(prepared)
            if getattr(prepared, field.name) in {secret_key, secret_value}
        }
        assert set(credential_fields) == {secret_key, secret_value}
        assert credential_fields[secret_key].repr is False
        assert credential_fields[secret_value].repr is False
        prepared_repr = repr(prepared)
        assert secret_key not in prepared_repr
        assert secret_value not in prepared_repr
    assert api.CANONICAL_BYBIT_API_BASE_URL == CANONICAL_BASE_URL


def test_source_audit_rejects_unreachable_sample_and_universe_policy_preflights(tmp_path):
    api = _api()
    audit_api = _audit_api()
    root = tmp_path / "unreachable-preflights"
    _write_source(
        root,
        "scripts/validate_sample_grid.py",
        """
        def main():
            settings = load_settings()
            if False:
                enforce_validate_only_settings(settings=settings)
            client = BybitClient(settings)
            return client
        """,
    )
    _write_source(
        root,
        "scripts/validate_universe_fgrid_constraints.py",
        """
        def main():
            settings = load_settings()
            if False:
                _enforce_validate_only_settings(settings=settings)
            settings.require_private_credentials()
            pool = ThreadPoolExecutor(max_workers=10)
            return pool
        """,
    )
    result = audit_api.audit_source_tree(root)
    joined = "\n".join(result.violations)
    assert result.ok is False
    assert "validate sample policy preflight must precede side effects" in joined
    assert "validate universe policy preflight must precede credentials and threads" in joined
    assert api.CANONICAL_FGRID_VALIDATE_ENDPOINT == CANONICAL_ENDPOINT


def test_universe_purge_runs_only_after_settings_policy_preflight(monkeypatch):
    api = _api()
    universe_api = importlib.import_module("scripts.validate_universe_fgrid_constraints")
    settings = _settings()
    events: list[str] = []

    def load_settings_for_purge():
        events.append("load_settings")
        return settings

    def policy_preflight_for_purge(*, settings):
        assert settings is settings_for_purge
        events.append("policy_preflight")

    def purge_after_preflight():
        events.append("purge")

    settings_for_purge = settings
    policy_bindings = [
        name
        for name, value in vars(universe_api).items()
        if value is api.enforce_validate_only_settings
    ]
    assert policy_bindings
    monkeypatch.setattr(universe_api, "load_settings", load_settings_for_purge)
    for binding in policy_bindings:
        monkeypatch.setattr(universe_api, binding, policy_preflight_for_purge)
    monkeypatch.setattr(universe_api, "purge_skipped_constraints", purge_after_preflight)
    monkeypatch.setattr(
        sys,
        "argv",
        ["validate_universe_fgrid_constraints.py", "--purge-skipped-constraints"],
    )

    assert universe_api.main() is None
    assert events == ["load_settings", "policy_preflight", "purge"]
    assert api.CANONICAL_BYBIT_ENV == "mainnet"


def test_private_transport_policy_drift_is_refused_after_limiter_before_dispatch(monkeypatch):
    api = _api()
    client_api = _client_api()
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: None,
    )
    monkeypatch.setattr(client_api, "sign_v5", lambda secret, target: "signature")

    redirect_deliveries: list[tuple[str, str | None]] = []

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        redirect_deliveries.append(
            (str(request.url), request.headers.get("X-BAPI-API-KEY"))
        )
        if request.url.host == "api.bybit.com":
            return httpx.Response(
                307,
                headers={"Location": "https://attacker.invalid/capture"},
                request=request,
            )
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {}},
            request=request,
        )

    redirect_events: list[str] = []
    with httpx.Client(
        base_url=CANONICAL_BASE_URL,
        trust_env=False,
        follow_redirects=False,
        transport=httpx.MockTransport(redirect_handler),
    ) as redirect_http:
        redirect_client = _client(_settings(), redirect_events, http=redirect_http)
        redirect_client.rate_limiter = _MutatingLimiter(
            redirect_events,
            lambda: setattr(redirect_http, "follow_redirects", True),
        )
        _assert_boundary_error(
            api,
            "private_http_policy_forbidden",
            lambda: redirect_client.private_get("/v5/account/info"),
        )
    assert redirect_deliveries == []

    trust_deliveries: list[str] = []

    def trust_handler(request: httpx.Request) -> httpx.Response:
        trust_deliveries.append(str(request.url))
        return httpx.Response(
            200,
            json={"retCode": 0, "retMsg": "OK", "result": {"checkCode": "0"}},
            request=request,
        )

    trust_events: list[str] = []
    with httpx.Client(
        base_url=CANONICAL_BASE_URL,
        trust_env=False,
        follow_redirects=False,
        transport=httpx.MockTransport(trust_handler),
    ) as trust_http:
        trust_client = _client(_settings(), trust_events, http=trust_http)
        trust_client.rate_limiter = _MutatingLimiter(
            trust_events,
            lambda: setattr(trust_http, "_trust_env", True),
        )
        _assert_boundary_error(
            api,
            "private_http_policy_forbidden",
            lambda: trust_client.validate_grid_bot(_payload()),
        )
    assert trust_deliveries == []


def test_retry_rejects_prepared_object_mutation_against_external_fingerprint(monkeypatch):
    api = _api()
    client_api = _client_api()
    monkeypatch.setattr(
        _config_api().Settings,
        "require_private_credentials",
        lambda self: None,
    )
    sign_targets: list[str] = []
    monkeypatch.setattr(
        client_api,
        "sign_v5",
        lambda secret, target: sign_targets.append(target) or "signature",
    )
    monkeypatch.setattr(client_api.BybitClient._private_get.retry, "sleep", lambda delay: None)
    monkeypatch.setattr(
        client_api.BybitClient._private_validate_post.retry,
        "sleep",
        lambda delay: None,
    )

    get_events: list[str] = []
    get_http = _FailingGetHttp(get_events)
    get_client = _client(_settings(), get_events, http=get_http)
    original_get = get_client._private_get
    captured_get: list[object] = []

    def get_with_prepared_mutation(prepared):
        captured_get.append(prepared)
        initial_query = "category=linear&symbol=BTCUSDT"
        initial_target = f"/v5/account/fee-rate?{initial_query}"
        query_fields = [
            field.name
            for field in fields(prepared)
            if getattr(prepared, field.name) == initial_query
        ]
        target_fields = [
            field.name
            for field in fields(prepared)
            if getattr(prepared, field.name) == initial_target
        ]
        assert len(query_fields) == 1
        assert len(target_fields) == 1

        def mutate_get_prepared():
            changed_query = "category=linear&symbol=ETHUSDT"
            object.__setattr__(prepared, query_fields[0], changed_query)
            object.__setattr__(
                prepared,
                target_fields[0],
                f"/v5/account/fee-rate?{changed_query}",
            )

        get_http.on_first = mutate_get_prepared
        return original_get(prepared)

    get_client._private_get = get_with_prepared_mutation
    _assert_boundary_error(
        api,
        "private_get_prepared_request_invalid",
        lambda: get_client.private_get(
            "/v5/account/fee-rate",
            {"category": "linear", "symbol": "BTCUSDT"},
        ),
    )
    assert len(get_http.calls) == 1
    assert get_events == ["rate_limit", "http"]
    assert len(sign_targets) == 1
    assert len(captured_get) == 1
    _assert_boundary_error(
        api,
        "private_get_prepared_request_invalid",
        lambda: client_api.BybitClient._private_get.__wrapped__(
            get_client,
            captured_get[0],
        ),
    )

    sign_targets.clear()
    post_events: list[str] = []
    post_http = _FailingHttp(post_events)
    post_client = _client(_settings(), post_events, http=post_http)
    original_post = post_client._private_validate_post
    captured_post: list[object] = []

    def post_with_prepared_mutation(prepared):
        captured_post.append(prepared)
        initial_body = json.dumps(_payload(), separators=(",", ":"), ensure_ascii=False)
        body_fields = [
            field.name
            for field in fields(prepared)
            if getattr(prepared, field.name) == initial_body
        ]
        assert len(body_fields) == 1

        def mutate_post_prepared():
            changed_payload = {**_payload(), "symbol": "ETHUSDT"}
            object.__setattr__(
                prepared,
                body_fields[0],
                json.dumps(changed_payload, separators=(",", ":"), ensure_ascii=False),
            )

        post_http.on_first = mutate_post_prepared
        return original_post(prepared)

    post_client._private_validate_post = post_with_prepared_mutation
    _assert_boundary_error(
        api,
        "validate_prepared_request_invalid",
        lambda: post_client.validate_grid_bot(_payload()),
    )
    assert len(post_http.calls) == 1
    assert post_events == ["rate_limit", "http"]
    assert len(sign_targets) == 1
    assert len(captured_post) == 1
    _assert_boundary_error(
        api,
        "validate_prepared_request_invalid",
        lambda: client_api.BybitClient._private_validate_post.__wrapped__(
            post_client,
            captured_post[0],
        ),
    )
