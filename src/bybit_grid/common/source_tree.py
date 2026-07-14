from __future__ import annotations
import hashlib
import json
from pathlib import Path


class SourceTreeError(ValueError):
    pass


INCLUDE_SUFFIX = {".py", ".md", ".toml", ".yml", ".yaml", ".gitignore"}
INCLUDE_EXACT = {".gitignore"}
EXCLUDE = {
    ".git",
    ".venv",
    "venv",
    "data",
    "reports",
    "logs",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def _safe_rel(p):
    s = p.as_posix()
    if s.startswith("/") or ".." in p.parts or "\\" in s or ":" in s:
        raise SourceTreeError("unsafe_path")
    return s


def build_source_tree_manifest(root: Path):
    root = Path(root)
    entries = []
    seen = set()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDE for part in rel.parts):
            continue
        if p.is_symlink():
            raise SourceTreeError(f"symlink:{rel.as_posix()}")
        if p.is_dir():
            continue
        if not p.is_file():
            raise SourceTreeError(f"non_regular:{rel.as_posix()}")
        if (
            p.suffix not in INCLUDE_SUFFIX
            and p.name not in INCLUDE_EXACT
            and not p.name.endswith(".json.example")
        ):
            continue
        s = _safe_rel(rel)
        if s in seen:
            raise SourceTreeError("duplicate_path")
        seen.add(s)
        text = p.read_text("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        entries.append({"path": s, "sha256": hashlib.sha256(text.encode()).hexdigest()})
    body = {"schema_version": "source_tree_manifest_v1", "files": entries}
    b = json.dumps(body, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    return {"manifest": body, "tree_sha256": hashlib.sha256(b).hexdigest()}
