from qa_workbench.integrations.http import GatewayError, GatewayRequest, GatewayResponse
from qa_workbench.sectest import checks as c


class Server:
    """Answers GETs from a table of path -> (status, headers)."""

    def __init__(self, routes: dict[str, tuple[int, dict[str, str]]] | None = None):
        self.routes = routes or {}
        self.requests: list[GatewayRequest] = []
        self.failure: GatewayError | None = None

    def get(self, request: GatewayRequest) -> GatewayResponse:
        self.requests.append(request)
        if self.failure:
            raise self.failure
        path = (
            "/" + request.url.split("/", 3)[-1] if request.url.count("/") > 2 else "/"
        )
        status, headers = self.routes.get(path, self.routes.get("*", (200, {})))
        return GatewayResponse(status, headers, b"")

    def post(self, request):  # pragma: no cover
        raise AssertionError("checks must only GET")


SECURE = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000",
}


def _probe(server: Server, url: str = "https://app.test/", **options) -> c.Probe:
    return c.Probe(server, url, **options)


def _titles(outcome: c.CheckOutcome) -> list[str]:
    return [f.title for f in outcome.findings]


def test_headers_missing_are_confirmed_findings_and_complete_ones_are_clean() -> None:
    bad = c.check_headers(_probe(Server({"*": (200, {})})))
    good = c.check_headers(_probe(Server({"*": (200, SECURE)})))

    assert "No Content-Security-Policy header" in _titles(bad)
    assert "Clickjacking protection missing" in _titles(bad)
    assert "No Strict-Transport-Security header" in _titles(bad)
    assert all(f.confirmed for f in bad.findings)
    assert good.findings == ()


def test_hsts_is_only_expected_over_https() -> None:
    outcome = c.check_headers(_probe(Server({"*": (200, SECURE)}), "http://app.test/"))
    without = {k: v for k, v in SECURE.items() if k != "Strict-Transport-Security"}
    plain = c.check_headers(_probe(Server({"*": (200, without)}), "http://app.test/"))

    assert outcome.findings == () and plain.findings == ()


def test_version_and_technology_disclosure() -> None:
    server = Server({"*": (200, {"Server": "nginx/1.18.0", "X-Powered-By": "Express"})})

    outcome = c.check_info_disclosure(_probe(server))

    assert len(outcome.findings) == 2
    assert "Server: nginx/1.18.0" in outcome.findings[0].detail
    quiet = c.check_info_disclosure(_probe(Server({"*": (200, {"Server": "nginx"})})))
    assert quiet.findings == ()


def test_cookie_flags_are_checked_without_recording_values() -> None:
    cookies = (
        "sessionid=SECRETVALUE123; Path=/, "
        "theme=dark; Path=/; Secure; HttpOnly; SameSite=Lax"
    )
    outcome = c.check_cookies(_probe(Server({"*": (200, {"Set-Cookie": cookies})})))

    titles = _titles(outcome)
    assert "Cookie 'sessionid' has no Secure flag" in titles
    assert "Cookie 'sessionid' has no HttpOnly flag" in titles
    assert not any("theme" in t for t in titles)
    session = [
        f for f in outcome.findings if "sessionid" in f.title and "HttpOnly" in f.title
    ]
    assert session[0].confirmed and session[0].severity == "medium"
    assert "SECRETVALUE123" not in repr(outcome)


def test_a_non_session_cookie_gap_is_only_a_hypothesis() -> None:
    outcome = c.check_cookies(
        _probe(Server({"*": (200, {"Set-Cookie": "theme=dark; Path=/"})}))
    )

    assert outcome.findings and all(not f.confirmed for f in outcome.findings)
    assert (
        c.check_cookies(_probe(Server({"*": (200, {})}))).note
        == "The response sets no cookies."
    )


def test_cors_reflection_wildcard_and_open_cases() -> None:
    allow, creds = "Access-Control-Allow-Origin", "Access-Control-Allow-Credentials"
    reflect = Server({"*": (200, {allow: c.PROBE_ORIGIN, creds: "true"})})
    wildcard_creds = Server({"*": (200, {allow: "*", creds: "true"})})
    wildcard = Server({"*": (200, {"Access-Control-Allow-Origin": "*"})})

    assert c.check_cors(_probe(reflect)).findings[0].severity == "high"
    assert c.check_cors(_probe(wildcard_creds)).findings[0].title.startswith("Wildcard")
    open_ = c.check_cors(_probe(wildcard)).findings[0]
    assert not open_.confirmed and open_.severity == "low"
    assert reflect.requests[0].headers["Origin"] == c.PROBE_ORIGIN
    assert c.check_cors(_probe(Server())).findings == ()


def test_https_redirect_check() -> None:
    redirects = Server({"*": (301, {"Location": "https://app.test/"})})
    serves = Server({"*": (200, {})})

    assert c.check_https_redirect(_probe(redirects, "http://app.test/")).findings == ()
    assert _titles(c.check_https_redirect(_probe(serves, "http://app.test/"))) == [
        "HTTP is not redirected to HTTPS"
    ]
    skipped = c.check_https_redirect(_probe(serves, "https://app.test/"))
    assert skipped.requests == 0 and "already HTTPS" in skipped.note


def test_unauthenticated_access_uses_only_the_paths_given() -> None:
    server = Server({"/admin": (200, {}), "/account": (401, {}), "/old": (302, {})})
    probe = _probe(server, protected_paths=("admin", "/account", "old"))

    outcome = c.check_unauthenticated_access(probe)

    assert [f.title for f in outcome.findings] == ["admin answers without credentials"]
    assert outcome.findings[0].severity == "high" and outcome.requests == 3
    assert all(r.headers == {} for r in server.requests)  # no credentials at all
    nothing = c.check_unauthenticated_access(_probe(Server()))
    assert nothing.requests == 0 and "nothing was tested" in nothing.note


def test_every_check_only_sends_get_requests() -> None:
    server = Server({"*": (200, SECURE)})
    probe = _probe(server, protected_paths=("admin",))

    for check in c.CHECKS.values():
        check(probe)

    assert server.requests  # and Server.post raises if anything tried a write
