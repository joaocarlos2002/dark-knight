import json

from fake_gitlab import PREFIX, FakeGateway, make_client

from qa_workbench.publishing.bugs import GitLabBugs


def _writer(gateway: FakeGateway) -> GitLabBugs:
    client = make_client(gateway)
    return GitLabBugs(client, client.base_url, client.project_name)


def test_a_file_is_uploaded_to_the_project_as_multipart() -> None:
    gateway = FakeGateway({PREFIX + "/uploads": {"markdown": "![a](/uploads/x/a.png)"}})

    markdown = _writer(gateway).upload("a.png", b"png")

    request = gateway.requests[0]
    assert markdown == "![a](/uploads/x/a.png)"
    assert request.files == {"file": ("a.png", b"png")} and request.body is None
    assert request.headers["PRIVATE-TOKEN"]


def test_the_issue_is_a_plain_issue_and_its_url_is_built_from_the_iid() -> None:
    gateway = FakeGateway({PREFIX + "/issues": {"iid": 9}})

    iid, url = _writer(gateway).create_issue("Login fails", "text")

    assert (iid, url) == (9, "https://gitlab.test/group/app/-/issues/9")
    assert gateway.requests[0].body == {
        "title": "Login fails",
        "description": "text",
        "issue_type": "issue",
    }
    assert "glpat" not in json.dumps(gateway.requests[0].body)
