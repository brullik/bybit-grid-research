# Gate 04 Final Hotfix — Real NumPy Environment Guard

## PM decision

Do not rebuild range candidates or outcomes. The full v2 outcome review pack already passes its correctness checker. This task only fixes NumPy environment detection and Windows workspace hygiene so the full test suite can pass.

## Safety

- Do not add live trading, create/close/order, Telegram, or backtest code.
- Do not touch outcome data partitions.
- Do not recreate a local `numpy/` shim.
- Real NumPy is mandatory for `numpy_fast`.

## 1. Fix the NumPy shadow guard

Current code rejects every NumPy path under the repository root:

```python
numpy_file.is_relative_to(project_root)
```

That is too broad because a legitimate virtual environment may be located at `<project_root>/.venv/Lib/site-packages/numpy/...`.

Reject only an actual project-local shadow module:

```python
project_numpy_dir = (project_root / "numpy").resolve()
project_numpy_file = (project_root / "numpy.py").resolve()

is_project_shadow = (
    numpy_file == project_numpy_file
    or numpy_file.is_relative_to(project_numpy_dir)
)

if not getattr(np, "__version__", None) or is_project_shadow:
    raise ModuleNotFoundError(...)
```

Do not reject a real NumPy installed under `.venv/site-packages`.

## 2. Pin a Python-3.14-compatible NumPy

The owner runs Python 3.14. Update `pyproject.toml` from:

```toml
"numpy>=1.26",
```

to:

```toml
"numpy>=2.3.4,<3",
```

This keeps a wheel-supported NumPy line for Python 3.14.

## 3. Fix tests

Replace the overly broad assertion:

```python
assert not numpy_file.is_relative_to(project_root)
```

with checks that reject only:

```text
<project_root>/numpy/__init__.py
<project_root>/numpy.py
```

Add a test that simulates a legitimate NumPy path inside `<project_root>/.venv/Lib/site-packages/numpy/__init__.py` and confirms that the path classification does not treat it as a project shim.

## 4. Add an environment doctor

Add `scripts/check_numeric_environment.py` that prints strict JSON:

```json
{
  "python_version": "...",
  "python_executable": "...",
  "numpy_version": "...",
  "numpy_file": "...",
  "numpy_is_project_shadow": false,
  "project_numpy_dir_exists": false,
  "project_numpy_py_exists": false,
  "numpy_fast_import_ok": true,
  "status": "ok"
}
```

Exit non-zero if:

- NumPy is missing;
- NumPy lacks `__version__`;
- NumPy resolves to `<project_root>/numpy` or `<project_root>/numpy.py`;
- `numpy_fast` cannot be imported.

## 5. Acceptance

```powershell
python scripts/check_numeric_environment.py
python -m pytest -q
ruff check .
```

Expected:

```text
status=ok
all tests passed
ruff passed
```

No range or outcome rebuild is required.
