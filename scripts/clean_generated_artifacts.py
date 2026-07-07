from __future__ import annotations

import shutil
from pathlib import Path

TARGETS = [
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data/processed/fgrid_validate_raw_redacted",
]


def main() -> None:
    removed = []
    for target in TARGETS:
        for path in Path(".").rglob(target) if target == "__pycache__" else [Path(target)]:
            if path.exists():
                shutil.rmtree(path)
                removed.append(path.as_posix())
    print("removed=" + ",".join(removed))


if __name__ == "__main__":
    main()
