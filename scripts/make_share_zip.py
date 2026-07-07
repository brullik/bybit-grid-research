from __future__ import annotations

import argparse
from pathlib import Path
import zipfile

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "data",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "reports/runs",
}
EXCLUDED_NAMES = {".env"}
EXCLUDED_PREFIXES = ("data/", "reports/runs/", "data/processed/fgrid_validate_raw_redacted/")
EXCLUDED_PARTS = {"private", "secret", "account"}


def should_exclude(path: Path) -> bool:
    rel = path.as_posix()
    if path.name in EXCLUDED_NAMES:
        return True
    if any(rel == d or rel.startswith(d + "/") for d in EXCLUDED_DIRS):
        return True
    if any(rel.startswith(p) for p in EXCLUDED_PREFIXES):
        return True
    lowered = rel.lower()
    return any(part in lowered for part in EXCLUDED_PARTS)


def make_zip(output: Path) -> int:
    count = 0
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(Path(".").rglob("*")):
            if not path.is_file():
                continue
            rel = Path(path.as_posix().removeprefix("./"))
            if rel == output or should_exclude(rel):
                continue
            zf.write(path, rel.as_posix())
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="bybit_grid_research_share.zip")
    args = parser.parse_args()
    out = Path(args.output)
    n = make_zip(out)
    print(f"zip={out} files={n}")


if __name__ == "__main__":
    main()
