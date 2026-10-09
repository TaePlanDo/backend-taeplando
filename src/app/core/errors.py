class AuthError(Exception):
    """Domain auth failure mapped to HTTP at the API edge."""

    def __init__(self, detail: str, *, status_code: int = 401) -> None:
        """Store the client-facing detail and HTTP status code."""
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
