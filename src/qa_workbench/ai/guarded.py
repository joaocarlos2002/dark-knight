"""An HTTP port that asks the action guard before every engine request (REQ-030).

The engines send the question and project context to a server. Without this, a
remote engine would receive them with no scope check, no rate limit, and no
trace. With it, each request is checked against the project's authorized hosts,
counted against the per-host rate limit, and written to the audit log (the
action and the URL, never the body or any header). A request that is not
allowed is never sent. A server on this machine is always in scope, and is still
audited.
"""

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from qa_workbench.ai.errors import ProviderRateLimited, ProviderUnavailable
from qa_workbench.ai.http import JsonHttp, JsonResponse
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import (
    ActionGuard,
    RateLimitExceeded,
    SecurityError,
    is_loopback,
)
from qa_workbench.security.policy import ActionRequest, Category
from qa_workbench.security.settings import load_settings

ACTOR = "ai-engine"


class GuardedJsonHttp:
    def __init__(self, inner: JsonHttp, guard: ActionGuard) -> None:
        self._inner = inner
        self._guard = guard

    def _authorize(self, method: str, url: str) -> None:
        host = urlsplit(url).hostname or url
        action = ActionRequest(
            f"send to AI engine {host}",
            Category.READ,
            f"{method} {url}",
            # A local server is always in scope; it is still audited.
            target_url="" if is_loopback(url) else url,
            requested_by=ACTOR,
        )
        try:
            self._guard.authorize(action)
        except RateLimitExceeded as error:
            raise ProviderRateLimited(host, str(error).rstrip(".")) from error
        except SecurityError as error:
            raise ProviderUnavailable(
                host,
                f"nothing was sent: {str(error).rstrip('.')}",
                hint=(
                    "Allow the host with `batman security set --project <id> "
                    f"--allow-host {host} --by <name>`"
                ),
            ) from error

    def request(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> JsonResponse:
        self._authorize(method, url)
        return self._inner.request(
            method, url, body=body, headers=headers, timeout=timeout
        )

    def stream_lines(
        self,
        method: str,
        url: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        self._authorize(method, url)
        return self._inner.stream_lines(
            method, url, body=body, headers=headers, timeout=timeout
        )


def guarded_http(inner: JsonHttp, project_root: Path) -> GuardedJsonHttp:
    """``inner`` behind the guard of the project at ``project_root``."""
    guard = ActionGuard(load_settings(project_root), AuditLog(project_root))
    return GuardedJsonHttp(inner, guard)
