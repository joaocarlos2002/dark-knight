from qa_workbench.core.secrets import find_secrets, redact_secrets


def test_literal_secrets_are_replaced_and_context_is_kept() -> None:
    text = "deploy ok\npassword=hunter22\ntoken: glpat-abcdefghijklmnop1234\nbye"

    cleaned = redact_secrets(text)

    assert "hunter22" not in cleaned and "glpat-abcdef" not in cleaned
    assert "deploy ok" in cleaned and "bye" in cleaned
    assert find_secrets(cleaned) == []


def test_placeholders_and_plain_text_are_untouched() -> None:
    text = "export PASSWORD=$PASSWORD and reset the password page"

    assert redact_secrets(text) == text


def test_known_token_formats_are_replaced_anywhere() -> None:
    assert redact_secrets("a ghp_" + "b" * 30 + " z") == "a [REDACTED] z"
    assert "AKIA" not in redact_secrets("k AKIAABCDEFGHIJKLMNOP")
