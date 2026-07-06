import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bybit_grid.logging import redact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_sprint_report(data_dir: Path, sections: dict[str, object]) -> Path:
    reports_dir = Path("reports")
    runs_dir = reports_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now_iso()
    run = {
        "command": sections.get("command", "unknown"),
        "started_at": sections.get("started_at", now),
        "ended_at": sections.get("ended_at", now),
        "status": sections.get("status", "ok"),
        "counts": sections.get("counts", {}),
        "output_paths": sections.get("output_paths", []),
        "error_summary": sections.get("error_summary", ""),
        "sections": redact(sections),
    }
    run_path = runs_dir / f"{now.replace(':', '').replace('+', 'Z')}_{uuid4().hex[:8]}.json"
    run_path.write_text(json.dumps(run, indent=2, sort_keys=True, default=str), encoding="utf-8")

    runs = []
    for path in sorted(runs_dir.glob("*.json")):
        try:
            runs.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    lines = ["# Sprint 01 API Report", "", f"Updated UTC: {now}", "", "## Runs", ""]
    for item in runs:
        lines += [
            f"### {item.get('command', 'unknown')} — {item.get('status', 'unknown')}",
            "",
            f"- started_at: {item.get('started_at', '')}",
            f"- ended_at: {item.get('ended_at', '')}",
            f"- counts: `{json.dumps(item.get('counts', {}), sort_keys=True)}`",
            f"- output_paths: `{json.dumps(item.get('output_paths', []), sort_keys=True)}`",
            f"- error_summary: {item.get('error_summary') or 'none'}",
            "",
        ]
        sections = item.get("sections", {})
        for key, value in sections.items():
            lines += [f"#### {key}", "", str(value), ""]
    report_path = reports_dir / "sprint_01_api_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
