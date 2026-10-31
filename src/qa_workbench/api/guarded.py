"""An HTTP transport that asks the action guard before every request (REQ-030).

Without this, an API definition could send requests to any host. With it, each
request is checked against the project's authorized hosts, counted against the
per-host rate limit, written to the audit log, and, when the policy says so,
held for a person's approval. A request that is not allowed is never sent: the
step ends as an error that says why and how to continue.
"""

from qa_workbench.api.errors import ApiNotAuthorized
from qa_workbench.api.sanitize import Sanitizer
from qa_workbench.api.transport import HttpTransport, PreparedRequest, TransportResponse
from qa_workbench.security.guard import ActionGuard, SecurityError, is_loopback
from qa_workbench.security.policy import ActionRequest, Category

ACTOR = "api-runner"
_READ_ONLY = frozenset({"GET", "HEAD", "OPTIONS"})


def category_for(method: str) -> Category:
    """What a request does to the target.

    Reading is a read. Deleting is a data change and always needs approval.
    Creating or updating is routine work on a test target: it asks first only
    in ``assisted`` mode.
    """
    method = method.upper()
    if method in _READ_ONLY:
        return Category.READ
    if method == "DELETE":
        return Category.DATA_CHANGE
    return Category.ROUTINE


class GuardedTransport:
    def __init__(self, inner: HttpTransport, guard: ActionGuard) -> None:
        self._inner = inner
        self._guard = guard
        self._sanitizer = Sanitizer()

    def send(self, request: PreparedRequest) -> TransportResponse:
        shown = self._sanitizer.url(request.url)
        action = ActionRequest(
            "api request",
            category_for(request.method),
            f"{request.method.upper()} {shown}",
            # A local server is always in scope; it is still audited.
            target_url="" if is_loopback(request.url) else request.url,
            requested_by=ACTOR,
        )
        try:
            self._guard.authorize(action)
        except SecurityError as error:
            raise ApiNotAuthorized(
                str(error), method=request.method, url=request.url
            ) from error
        return self._inner.send(request)
