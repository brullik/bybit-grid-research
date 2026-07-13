#!/usr/bin/env python
from __future__ import annotations
import argparse
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ALLOWED = ("https://api.bybit.com", "https://api.bytick.com")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", required=True, choices=ALLOWED)
    p.add_argument("--timeout-seconds", type=int, required=True)
    p.add_argument("--attempts", type=int, default=3)
    a = p.parse_args(argv)
    if not (1 <= a.timeout_seconds <= 120):
        p.error("--timeout-seconds must be 1..120")
    if not (1 <= a.attempts <= 10):
        p.error("--attempts must be 1..10")
    attempts = []
    for i in range(1, a.attempts + 1):
        start = time.perf_counter()
        ok = False
        typ = None
        status = None
        try:
            r = urlopen(
                Request(
                    a.base_url + "/v5/market/time",
                    method="GET",
                    headers={"Accept": "application/json"},
                ),
                timeout=a.timeout_seconds,
            )
            try:
                status = int(getattr(r, "status", r.getcode()))
                r.read()
                ok = 200 <= status < 300
                typ = "ok" if ok else "http_status"
            finally:
                if hasattr(r, "close"):
                    r.close()
        except HTTPError as e:
            status = int(e.code)
            typ = "HTTPError"
            try:
                e.read()
            finally:
                if hasattr(e, "close"):
                    e.close()
        except (URLError, TimeoutError, OSError) as e:
            typ = type(e).__name__
        attempts.append(
            {
                "attempt": i,
                "ok": ok,
                "failure_type": None if ok else typ,
                "http_status": status,
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
            }
        )
    out = {
        "base_url": a.base_url,
        "attempt_count": a.attempts,
        "attempts": attempts,
        "ok": any(x["ok"] for x in attempts),
    }
    print(json.dumps(out, sort_keys=True, separators=(",", ":")))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
