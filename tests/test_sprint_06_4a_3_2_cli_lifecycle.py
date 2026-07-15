import os
import subprocess
import sys


def test_audit_cli_help_is_real_subprocess():
    r = subprocess.run([sys.executable, "-m", "bybit_grid.cli.market_store_audit", "--help"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={**os.environ, "PYTHONPATH": "src"})
    assert r.returncode == 0
