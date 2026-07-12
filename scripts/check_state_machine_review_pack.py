from __future__ import annotations
import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from bybit_grid.backtest.neutral_grid.evidence import (
    FALSE_GUARDRAILS,
    MEMBERS,
    RUN_ID,
    EvidenceError,
    validate_artifact_bundle,
    validate_manifest,
    validate_member_names,
)


def emit(o, code=0):
    print(json.dumps(o, sort_keys=True, separators=(",", ":")))
    return code


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("pack_path", nargs="?")
    p.add_argument("--zip", dest="zip_path")
    p.add_argument("--run-id", default=RUN_ID)
    a = p.parse_args(argv)
    if a.pack_path and a.zip_path and a.pack_path != a.zip_path:
        return emit({"review_pack_ok": False, "error": "conflicting_pack_paths"}, 1)
    path = a.zip_path or a.pack_path
    if not path:
        return emit({"review_pack_ok": False, "error": "missing_pack_path"}, 1)
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            validate_member_names(names)
            data = {n: z.read(n) for n in names}
        validate_manifest(data[MEMBERS[0]], data, a.run_id)
        summary = validate_artifact_bundle({m: data[m] for m in MEMBERS[1:]}, a.run_id)
        return emit(
            {
                "review_pack_ok": True,
                "run_id": a.run_id,
                "member_count": 12,
                "hashes_verified": 11,
                "canonical_scenario_count": 33,
                **summary,
                **FALSE_GUARDRAILS,
            },
            0,
        )
    except FileNotFoundError:
        return emit({"review_pack_ok": False, "error": "missing_zip", "path": path}, 1)
    except zipfile.BadZipFile:
        return emit({"review_pack_ok": False, "error": "bad_zip", "path": path}, 1)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return emit(
            {"review_pack_ok": False, "error": "malformed_json_or_unicode", "path": path}, 1
        )
    except EvidenceError as e:
        return emit({"review_pack_ok": False, "error": e.error, **e.extra}, 1)
    except Exception as e:
        return emit(
            {"review_pack_ok": False, "error": type(e).__name__, "error_summary": str(e)[:200]}, 1
        )


if __name__ == "__main__":
    sys.exit(main())
