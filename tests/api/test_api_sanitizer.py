from qa_workbench.api.sanitize import REDACTED, Sanitizer
from qa_workbench.core.secrets import find_secrets


def test_sensitive_headers_are_hidden_by_name_and_others_kept() -> None:
    headers = Sanitizer().headers(
        {
            "Authorization": "Bearer abcdefgh12345678",
            "Cookie": "sid=1",
            "X-Api-Key": "k",
            "X-Session-Id": "s",
            "Accept": "application/json",
        }
    )

    assert headers["Authorization"] == REDACTED
    assert headers["Cookie"] == REDACTED
    assert headers["X-Api-Key"] == REDACTED
    assert headers["X-Session-Id"] == REDACTED
    assert headers["Accept"] == "application/json"


def test_urls_lose_user_info_and_credential_query_values() -> None:
    url = Sanitizer().url("https://bob:pw@api.test/x?api_key=abc&page=2")

    assert "bob" not in url and "pw@" not in url
    assert "abc" not in url and "page=2" in url


def test_json_keys_and_nested_values_are_sanitized() -> None:
    body = Sanitizer().body(
        b'{"user": {"password": "hunter22", "name": "ada"}, '
        b'"items": [{"access_token": "zzzz1234"}], "note": "ok"}'
    )

    assert "hunter22" not in body and "zzzz1234" not in body
    assert "ada" in body and "ok" in body


def test_known_secret_values_are_removed_wherever_they_appear() -> None:
    sanitizer = Sanitizer(["s3cr3t-value"])

    assert "s3cr3t" not in sanitizer.text("echo: s3cr3t-value done")
    assert "s3cr3t" not in sanitizer.body('{"message": "got s3cr3t-value"}')


def test_credential_shapes_are_found_in_plain_text() -> None:
    sanitizer = Sanitizer()
    text = (
        "Authorization: Bearer abcdefghijklmnop1234 and "
        "password=hunter22 and AKIAABCDEFGHIJKLMNOP"
    )

    cleaned = sanitizer.text(text)

    assert "hunter22" not in cleaned and "abcdefghijklmnop" not in cleaned
    assert "AKIAABCDEFGHIJKLMNOP" not in cleaned
    assert not find_secrets(cleaned)


def test_placeholders_are_left_alone() -> None:
    assert Sanitizer().text("password=$PASSWORD") == "password=$PASSWORD"


def test_personal_data_is_masked_unless_turned_off() -> None:
    text = "ada@example.com 123.456.789-09"

    masked = Sanitizer().text(text)
    kept = Sanitizer(mask_personal_data=False).text(text)

    assert "example.com" not in masked and "789-09" not in masked
    assert kept == text


def test_long_bodies_are_truncated_and_empty_bodies_are_empty() -> None:
    sanitizer = Sanitizer(max_body=50)

    assert sanitizer.body("x" * 500).endswith("[truncated]")
    assert sanitizer.body(b"") == "" and sanitizer.body(None) == ""


def test_undecodable_bytes_do_not_crash() -> None:
    assert Sanitizer().body(b"\xff\xfe binary") != ""
