"""Errors raised by the Browser Agent.

They keep what was being done (action, selector, URL) so a failure can be
diagnosed, and they separate three kinds of problem: the browser could not do
its job (:class:`BrowserError`), the page did not behave as expected
(:class:`AssertionFailed`), and the browser is not set up (:class:`BrowserSetupError`).
"""


class BrowserError(Exception):
    """The browser could not perform an action (infrastructure or test fault)."""

    def __init__(
        self,
        message: str,
        *,
        action: str | None = None,
        selector: str | None = None,
        url: str | None = None,
    ) -> None:
        details = [
            f"{name}={value!r}"
            for name, value in (
                ("action", action),
                ("selector", selector),
                ("url", url),
            )
            if value
        ]
        suffix = f" ({', '.join(details)})" if details else ""
        super().__init__(f"{message}{suffix}")
        self.action = action
        self.selector = selector
        self.url = url


class BrowserTimeout(BrowserError):
    """An action or navigation did not finish in time."""


class AssertionFailed(Exception):
    """The page does not match what the test expected: a product finding.

    Deliberately not a :class:`BrowserError`, so a failed check is never
    confused with a browser fault.
    """

    def __init__(self, message: str, *, expected: str, actual: str) -> None:
        super().__init__(f"{message} (expected {expected!r}, found {actual!r})")
        self.expected = expected
        self.actual = actual


class BrowserSetupError(Exception):
    """Playwright or its browsers are missing, or installing them failed."""
