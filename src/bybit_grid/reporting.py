from datetime import datetime, timezone
from pathlib import Path

def write_sprint_report(data_dir: Path, sections: dict[str, object]) -> Path:
    path=Path('reports')/'sprint_01_api_report.md'; path.parent.mkdir(exist_ok=True)
    lines=['# Sprint 01 API Report','',f'Run UTC: {datetime.now(timezone.utc).isoformat()}','']
    for k,v in sections.items(): lines += [f'## {k}', '', str(v), '']
    path.write_text('\n'.join(lines), encoding='utf-8'); return path
