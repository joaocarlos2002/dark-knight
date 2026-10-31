"""Errors raised by the API runner."""


class ApiError(Exception):
    """The API test could not be defined, run, or saved."""


class ApiDefinitionError(ApiError):
    """A test definition is invalid (reported with every problem found)."""


class ApiTransportError(ApiError):
    """The request could not be completed (connection, TLS, timeout)."""

    def __init__(self, message: str, *, method: str, url: str) -> None:
        super().__init__(f"{method} {url}: {message}")
        self.method = method
        self.url = url
        self.reason = message


class ApiNotAuthorized(ApiTransportError):
    """The security policy did not allow the request, so nothing was sent."""


class UnsafeToPersistError(ApiError):
    """Output still looked like it held a credential, so it was not saved."""
