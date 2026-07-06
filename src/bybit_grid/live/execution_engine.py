from bybit_grid.config import Settings


class ExecutionEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def create_grid_bot(self, *, runtime_live: bool = False):
        self.settings.assert_live_trading_allowed(runtime_live)
        raise NotImplementedError("Forbidden in Sprint 01")

    def close_grid_bot(self, *, runtime_live: bool = False):
        self.settings.assert_live_trading_allowed(runtime_live)
        raise NotImplementedError("Forbidden in Sprint 01")
