from __future__ import annotations

import argparse
from pathlib import Path
import sys
import zipfile

BAD_DIRS = {"data", "reports", ".pytest_cache", ".ruff_cache", "__pycache__"}


def is_sensitive_or_generated(name: str) -> bool:
    p = Path(name)
    parts = set(p.parts)
    if BAD_DIRS & parts:
        return True
    base = p.name
    if base == ".env" or (base.startswith(".env.") and base != ".env.example"):
        return True
    return base.endswith(".pyc")


def check_zip(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return [n for n in zf.namelist() if is_sensitive_or_generated(n)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check that share archives do not contain secrets/generated artifacts.")
    parser.add_argument("zip", nargs="?", help="Optional manual zip to inspect")
    args = parser.parse_args()
    if args.zip:
        offenders = check_zip(Path(args.zip))
        if offenders:
            print("share_hygiene status=fail offenders=" + ",".join(offenders[:50]))
            sys.exit(1)
        print(f"share_hygiene status=ok zip={args.zip}")
        return
    candidates = sorted(Path(".").glob("*.zip"))
    for z in candidates:
        offenders = check_zip(z)
        if offenders:
            print("share_hygiene status=fail zip=" + z.as_posix() + " offenders=" + ",".join(offenders[:50]))
            sys.exit(1)
    print(f"share_hygiene status=ok zips_checked={len(candidates)}")

if __name__ == "__main__":
    main()
