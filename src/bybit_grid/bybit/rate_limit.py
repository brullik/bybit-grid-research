import time
class SimpleRateLimiter:
    def __init__(self, min_interval_s: float = 0.05): self.min_interval_s=min_interval_s; self._last=0.0
    def wait(self) -> None:
        now=time.monotonic(); sleep_for=self.min_interval_s-(now-self._last)
        if sleep_for>0: time.sleep(sleep_for)
        self._last=time.monotonic()
