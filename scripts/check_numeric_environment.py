#!/usr/bin/env python
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _is_project_numpy_shadow(numpy_file: Path, project_root: Path) -> bool:
    project_numpy_dir = (project_root / "numpy").resolve()
    project_numpy_file = (project_root / "numpy.py").resolve()
    numpy_file = numpy_file.resolve()
    return numpy_file == project_numpy_file or numpy_file.is_relative_to(project_numpy_dir)


def _emit(payload: dict[str, Any], exit_code: int) -> None:
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    raise SystemExit(exit_code)


def main() -> None:
    payload: dict[str, Any] = {
        "python_version": sys.version,
        "python_executable": sys.executable,
        "numpy_version": None,
        "numpy_file": None,
        "numpy_is_project_shadow": None,
        "project_numpy_dir_exists": (PROJECT_ROOT / "numpy").exists(),
        "project_numpy_py_exists": (PROJECT_ROOT / "numpy.py").exists(),
        "numpy_fast_import_ok": False,
        "status": "error",
    }

    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        payload["error"] = f"numpy import failed: {exc}"
        _emit(payload, 1)

    numpy_version = getattr(np, "__version__", None)
    numpy_file_attr = getattr(np, "__file__", None)
    numpy_file = Path(numpy_file_attr).resolve() if numpy_file_attr else None
    is_shadow = bool(numpy_file and _is_project_numpy_shadow(numpy_file, PROJECT_ROOT))

    payload.update(
        {
            "numpy_version": numpy_version,
            "numpy_file": str(numpy_file) if numpy_file else None,
            "numpy_is_project_shadow": is_shadow,
        }
    )

    if not numpy_version:
        payload["error"] = "numpy lacks __version__"
        _emit(payload, 1)
    if is_shadow:
        payload["error"] = "numpy resolves to a project-local shadow module"
        _emit(payload, 1)

    try:
        import bybit_grid.research.range_core.numpy_fast  # noqa: F401
    except Exception as exc:
        payload["error"] = f"numpy_fast import failed: {type(exc).__name__}: {exc}"
        _emit(payload, 1)

    payload["numpy_fast_import_ok"] = True
    payload["status"] = "ok"
    _emit(payload, 0)


if __name__ == "__main__":
    main()
