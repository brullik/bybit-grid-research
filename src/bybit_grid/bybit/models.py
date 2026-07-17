class BybitAPIError(RuntimeError):
    def __init__(
        self,
        endpoint: str,
        status_code: int | None,
        ret_code: int | str | None,
        ret_msg: str | None,
        debug_msg: str | None = None,
        response_data: dict | None = None,
    ):
        super().__init__(
            f"Bybit API error endpoint={endpoint} status_code={status_code} retCode={ret_code} retMsg={ret_msg} debug={debug_msg}"
        )
        self.endpoint = endpoint
        self.status_code = status_code
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.debug_msg = debug_msg
        self.response_data = response_data or {}

# RED probe after frozen erratum: strict API response envelope implementation intentionally unavailable.
