import threading
import time


class SimpleRateLimiter:
    def __init__(self, min_interval_s: float = 0.05):
        self.min_interval_s = min_interval_s
        self._last = 0.0
        self._lock = threading.Lock()
        self.wait_count = 0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self.min_interval_s - (now - self._last)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()
            self.wait_count += 1


class TokenBucketRateLimiter:
    def __init__(self, requests_per_second: float):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.min_interval_s = 1.0 / requests_per_second
        self._last = 0.0
        self._lock = threading.Lock()
        self.wait_count = 0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self.min_interval_s - (now - self._last)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()
            self.wait_count += 1
