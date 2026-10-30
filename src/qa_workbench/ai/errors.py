"""Provider failures. None is turned into an empty answer (NFR-010)."""


class ProviderError(Exception):
    """A provider call failed. ``provider`` says which one."""

    def __init__(self, provider: str, message: str, *, hint: str = "") -> None:
        text = f"{provider}: {message}"
        super().__init__(f"{text}. {hint}" if hint else text)
        self.provider = provider
        self.hint = hint


class ProviderUnavailable(ProviderError):
    """Not installed, not running, or unreachable."""


class ProviderTimeout(ProviderError):
    """No answer within the time limit."""


class ProviderRateLimited(ProviderError):
    """The provider asked to slow down."""


class ProviderResponseError(ProviderError):
    """The provider answered with something unusable."""


class ProviderCancelled(ProviderError):
    """The caller cancelled the request."""


class CapabilityNotSupported(ProviderError):
    """The provider cannot do what was asked (for example tool calls)."""


class NoProviderAvailable(Exception):
    """Selection found no usable provider; the message says why for each."""
