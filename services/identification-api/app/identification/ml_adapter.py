class MLUnavailableError(RuntimeError):
    pass


class MLAdapter:
    async def identify(self, facts: list[dict]) -> list[dict]:
        raise MLUnavailableError("ML provider is not configured")
