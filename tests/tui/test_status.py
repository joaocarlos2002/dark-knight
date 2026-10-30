import pytest

from qa_workbench.tui.status import Status, format_status, parse_status, style_for


def test_every_status_has_a_symbol_and_a_label() -> None:
    for status in Status:
        style = style_for(status)
        assert style.symbol
        assert style.label


def test_status_is_readable_without_color() -> None:
    assert format_status(Status.PASSED) == "✓ PASSED"
    assert format_status(Status.FAILED) == "✗ FAILED"
    assert format_status(Status.BLOCKED) == "⊘ BLOCKED"


def test_negative_states_are_not_all_errors() -> None:
    assert style_for(Status.FAILED).tone == "error"
    assert style_for(Status.BLOCKED).tone != "error"
    assert style_for(Status.INCONCLUSIVE).tone != "error"
    assert style_for(Status.CANCELLED).tone != "error"


def test_parse_status_is_case_insensitive() -> None:
    assert parse_status(" Running ") is Status.RUNNING


def test_unknown_status_is_rejected_with_the_valid_names() -> None:
    with pytest.raises(ValueError, match="Unknown status 'flaky'") as error:
        parse_status("flaky")

    assert "passed" in str(error.value)


def test_warning_and_ai_processing_are_part_of_the_vocabulary() -> None:
    assert format_status(Status.WARNING) == "▲ WARNING"
    assert format_status(Status.AI) == "✦ AI PROCESSING"
    assert style_for(Status.WARNING).tone == "warning"
    assert style_for(Status.AI).tone == "ai"
