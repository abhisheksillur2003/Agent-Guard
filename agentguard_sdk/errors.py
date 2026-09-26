class AgentGuardError(Exception):
    """Base class for errors that must stop the requested tool action."""


class AgentGuardConfigurationError(AgentGuardError):
    """The client configuration cannot protect credentials or address the API."""


class AgentGuardUnavailableError(AgentGuardError):
    """The API could not produce a trustworthy decision."""


class AgentGuardProtocolError(AgentGuardError):
    """The API returned a malformed or unexpected response."""


class AgentGuardAPIError(AgentGuardError):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        request_id: str | None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.request_id = request_id
        suffix = f" (request {request_id})" if request_id else ""
        super().__init__(f"AgentGuard rejected the request [{code}]: {message}{suffix}")
