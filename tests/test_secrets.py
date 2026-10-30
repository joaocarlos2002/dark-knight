import pytest

from qa_workbench.core.secrets import find_secrets


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("password=hunter2", ["a literal password value"]),
        ("Password: Sup3rS3cret!", ["a literal password value"]),
        ("api_key = abcd1234", ["a literal api_key value"]),
        ('{"token": "abc.def"}', ["a literal token value"]),
        ("authorization: Basic dXNlcjpwdw==", ["a literal authorization value"]),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sig", ["a JSON Web Token"]),
        ("key AKIAABCDEFGHIJKLMNOP here", ["an AWS access key"]),
        ("ghp_" + "a" * 36, ["a GitHub token"]),
        ("-----BEGIN RSA PRIVATE KEY-----", ["a private key"]),
        ("Bearer " + "a1B2" * 8, ["a bearer token"]),
    ],
)
def test_literal_secrets_are_found(text: str, expected: list[str]) -> None:
    assert find_secrets(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Enter the password and click Sign in",
        "The password field is required",
        "Reset password link is e-mailed",
        "password=$TEST_PASSWORD",
        "password: <valid password>",
        "token={{token}}",
        "password: ****",
        "api_key=${API_KEY}",
        "secret=%SECRET%",
        "Use the token from the environment",
        "",
    ],
)
def test_prose_and_placeholders_are_not_secrets(text: str) -> None:
    assert find_secrets(text) == []


def test_every_secret_in_a_text_is_listed() -> None:
    text = "password=hunter2 and token=abc123"

    assert find_secrets(text) == [
        "a literal password value",
        "a literal token value",
    ]
