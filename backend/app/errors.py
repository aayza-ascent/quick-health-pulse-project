"""Domain errors and their HTTP representation.

Junction is a third-party dependency that can be slow, rate-limited or
misconfigured. Each failure mode gets its own exception so the API layer can
translate it into a response the UI is able to explain to the user, rather than
collapsing everything into an opaque 500.
"""

from http import HTTPStatus


class HealthPulseError(Exception):
    """Base class for errors this service knows how to report."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    code: str = "internal_error"
    message: str = "Something went wrong."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        if message:
            self.message = message


class ConfigurationError(HealthPulseError):
    """The service was asked to use Junction but has not been configured for it."""

    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "not_configured"
    message = "Junction credentials are not configured for this service."


class JunctionError(HealthPulseError):
    """Base class for failures originating from the Junction API."""

    status_code = HTTPStatus.BAD_GATEWAY
    code = "junction_error"
    message = "Junction returned an unexpected response."


class JunctionAuthError(JunctionError):
    status_code = HTTPStatus.BAD_GATEWAY
    code = "junction_unauthorised"
    message = "Junction rejected the API key. Check JUNCTION_API_KEY."


class JunctionNotFoundError(JunctionError):
    status_code = HTTPStatus.NOT_FOUND
    code = "junction_not_found"
    message = "Junction has no record of this user."


class JunctionRateLimitError(JunctionError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "junction_rate_limited"
    message = "Junction is rate-limiting requests. Try again shortly."


class JunctionUnavailableError(JunctionError):
    status_code = HTTPStatus.SERVICE_UNAVAILABLE
    code = "junction_unavailable"
    message = "Could not reach Junction."
