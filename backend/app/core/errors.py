from http import HTTPStatus


class ApplicationError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class AuthenticationError(ApplicationError):
    def __init__(self, message: str = "Invalid or expired credentials") -> None:
        super().__init__(HTTPStatus.UNAUTHORIZED, "AUTHENTICATION_FAILED", message)


class AuthorizationError(ApplicationError):
    def __init__(self, message: str = "You are not authorized to perform this action") -> None:
        super().__init__(HTTPStatus.FORBIDDEN, "AUTHORIZATION_FAILED", message)


class NotFoundError(ApplicationError):
    def __init__(self, resource: str) -> None:
        super().__init__(HTTPStatus.NOT_FOUND, "NOT_FOUND", f"{resource} was not found")


class ConflictError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(HTTPStatus.CONFLICT, "CONFLICT", message)


class ValidationError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(HTTPStatus.UNPROCESSABLE_ENTITY, "VALIDATION_FAILED", message)


class DependencyUnavailableError(ApplicationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(HTTPStatus.SERVICE_UNAVAILABLE, code, message)


class UpstreamResponseError(ApplicationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(HTTPStatus.BAD_GATEWAY, code, message)
