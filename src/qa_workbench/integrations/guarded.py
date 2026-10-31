"""An HTTP gateway that asks the action guard before every request (REQ-030).

Reading from GitLab sends the project's token to a server. Without this, any
``--url`` (or a repository URL typed into a project) would receive it, with no
rate limit and no trace. With it, each request is checked against the project's
authorized hosts, counted against the per-host rate limit, and written to the
audit log. A request that is not allowed is never sent.
"""

from qa_workbench.integrations.errors import NotAuthorizedError
from qa_workbench.integrations.http import GatewayRequest, GatewayResponse, HttpGateway
from qa_workbench.security.guard import ActionGuard, SecurityError, is_loopback
from qa_workbench.security.policy import ActionRequest, Category

ACTOR = "gitlab-reader"


class GuardedGateway:
    def __init__(self, inner: HttpGateway, guard: ActionGuard, system: str) -> None:
        self._inner = inner
        self._guard = guard
        self._system = system

    def get(self, request: GatewayRequest) -> GatewayResponse:
        action = ActionRequest(
            f"read {self._system}",
            Category.READ,
            f"GET {request.url}",
            # A local server is always in scope; it is still audited.
            target_url="" if is_loopback(request.url) else request.url,
            requested_by=ACTOR,
        )
        try:
            self._guard.authorize(action)
        except SecurityError as error:
            raise NotAuthorizedError(
                self._system,
                str(error).rstrip("."),
                hint="Allow the host with `batman security set --allow-host`",
            ) from error
        return self._inner.get(request)

    def post(self, request: GatewayRequest) -> GatewayResponse:
        # Writes have their own approval flow (publishing); a reader never posts.
        raise NotAuthorizedError(self._system, "this reader only sends GET requests")
