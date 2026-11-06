class DomainError(Exception):
    """An expected business failure safe to expose to clients."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        retry_after: int | None = None,
    ) -> None:
        self.retry_after = retry_after
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)
