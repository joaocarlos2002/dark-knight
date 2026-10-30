from pathlib import Path

import pytest

from qa_workbench.api.definition import load_definition
from qa_workbench.api.errors import ApiDefinitionError

VALID = """
name: Login flow
base_url: https://api.test
timeout_seconds: 5
steps:
  - name: login
    method: post
    url: /login
    json: {user: ada}
    auth: {type: bearer, env: API_TOKEN}
    expect:
      status: [200, 201]
      max_ms: 500
      json_schema: {type: object}
    extract:
      sid: {path: $.session, secret: true}
      uid: $.id
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "api.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_definition_is_loaded(tmp_path: Path) -> None:
    definition = load_definition(_write(tmp_path, VALID))

    step = definition.steps[0]
    assert definition.name == "Login flow" and definition.timeout_seconds == 5
    assert step.method == "POST" and step.auth.env == "API_TOKEN"
    assert step.expect.status == (200, 201) and step.expect.max_ms == 500
    assert step.extract["sid"].secret and not step.extract["uid"].secret


def test_every_problem_is_reported_at_once(tmp_path: Path) -> None:
    text = """
name: ""
base_url: ftp://nope
steps:
  - name: a
    method: FETCH
    url: ""
    json: {}
    body: x
    auth: {type: basic, env: P}
    expect: {status: ok, max_ms: -1, json_schema: {type: banana}}
  - name: a
    url: /x
"""
    with pytest.raises(ApiDefinitionError) as error:
        load_definition(_write(tmp_path, text))

    message = str(error.value)
    for expected in (
        "name is required",
        "base_url must start",
        "method 'FETCH'",
        "url is required",
        "either json or body",
        "needs 'user_env'",
        "expect.status",
        "max_ms",
        "json_schema is invalid",
        "used more than once",
    ):
        assert expected in message, expected


def test_literal_credentials_in_the_file_are_refused(tmp_path: Path) -> None:
    text = VALID + "    headers: {X-Debug: 'password=hunter22'}\n"

    with pytest.raises(ApiDefinitionError, match="use an environment variable"):
        load_definition(_write(tmp_path, text))


def test_unreadable_or_broken_files_are_explicit(tmp_path: Path) -> None:
    with pytest.raises(ApiDefinitionError, match="Cannot read"):
        load_definition(tmp_path / "missing.yaml")
    with pytest.raises(ApiDefinitionError, match="Cannot read"):
        load_definition(_write(tmp_path, "a: [unclosed"))
    with pytest.raises(ApiDefinitionError, match="must be a mapping"):
        load_definition(_write(tmp_path, "- just\n- a list\n"))
