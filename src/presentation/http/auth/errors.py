"""Auth domain errors — raised in the dependency, caught by exception handlers."""


class AuthenticationError(Exception):
    """Raised when a request cannot be authenticated (missing or invalid token)."""

    def __init__(self, detail: str = "Could not validate credentials", authenticate_value: str = "Bearer") -> None:
        self.detail = detail
        self.authenticate_value = authenticate_value
        super().__init__(detail)


class AuthorizationError(Exception):
    """Raised when an authenticated user lacks the required scopes/roles."""

    def __init__(self, required: list[str], authenticate_value: str = "Bearer") -> None:
        self.required = required
        self.authenticate_value = authenticate_value
        super().__init__(f"Insufficient permissions — required: {required}")
