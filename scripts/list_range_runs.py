from pathlib import Path
root = Path('data/processed/range_runs')
latest = (root/'latest_run.txt').read_text().strip() if (root/'latest_run.txt').exists() else ''
for p in sorted([x for x in root.iterdir() if x.is_dir()] if root.exists() else []):
    print(f"{p.name}{' latest' if p.name == latest else ''}")
