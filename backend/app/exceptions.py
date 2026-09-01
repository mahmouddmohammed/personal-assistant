"""Domain-level exceptions, translated to HTTP responses at the controller layer."""


class AppError(Exception):
    """Base class for all application errors."""

    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class UserAlreadyExistsError(AppError):
    status_code = 409


class InvalidCredentialsError(AppError):
    status_code = 401


class NotFoundError(AppError):
    status_code = 404


class ForbiddenError(AppError):
    status_code = 403


class ConversationNotFoundError(NotFoundError):
    pass
