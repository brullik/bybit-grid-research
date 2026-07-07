from __future__ import annotations


def funding_status(actual: int, expected_approx: int | None) -> str:
    if actual <= 0:
        return "missing"
    if expected_approx is None or expected_approx <= 0:
        return "unknown_interval"
    return "ok" if actual >= max(1, int(expected_approx * 0.8)) else "low"
