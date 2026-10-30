import pytest

from qa_workbench.requirements.parser import parse_markdown, parse_text

MARKDOWN = """# Login requirements

Intro text that is not a requirement.

## Users can log in with valid credentials

Priority: high
Status: draft
Tags: auth, login
Author: Ana

A registered user signs in with e-mail and password.

Acceptance criteria:
- The user reaches the dashboard.
- A wrong password shows an error.

## Users can reset their password

Prioridade: alta

### Critérios de aceitação
1. A link is e-mailed.
2. The link expires in one hour.
"""


def test_each_second_level_section_is_a_requirement() -> None:
    result = parse_markdown(MARKDOWN)

    assert result.issues == []
    assert [r.title for r in result.requirements] == [
        "Users can log in with valid credentials",
        "Users can reset their password",
    ]


def test_metadata_description_and_criteria_are_separated() -> None:
    first = parse_markdown(MARKDOWN).requirements[0]

    assert first.priority == "high"
    assert first.status == "draft"
    assert first.tags == ("auth", "login")
    assert first.author == "Ana"
    assert first.description == "A registered user signs in with e-mail and password."
    assert first.acceptance_criteria == (
        "The user reaches the dashboard.",
        "A wrong password shows an error.",
    )
    assert first.line == 5


def test_portuguese_keys_and_values_are_understood() -> None:
    second = parse_markdown(MARKDOWN).requirements[1]

    assert second.priority == "high"
    assert second.acceptance_criteria == (
        "A link is e-mailed.",
        "The link expires in one hour.",
    )
    assert second.description == ""


def test_a_document_without_second_level_sections_is_one_requirement() -> None:
    result = parse_markdown("# Export reports\n\nPriority: low\n\nUsers export PDFs.\n")

    assert [r.title for r in result.requirements] == ["Export reports"]
    assert result.requirements[0].priority == "low"
    assert result.requirements[0].description == "Users export PDFs."


def test_criteria_subsections_do_not_split_a_single_requirement() -> None:
    text = (
        "# Export\n\nUsers export PDFs.\n\n"
        "## Acceptance criteria\n- A file downloads.\n"
    )

    result = parse_markdown(text)

    assert [r.title for r in result.requirements] == ["Export"]
    assert result.requirements[0].acceptance_criteria == ("A file downloads.",)


def test_checklist_items_are_criteria() -> None:
    text = "## R\n\nAcceptance criteria:\n- [ ] one\n- [x] two\n"

    assert parse_markdown(text).requirements[0].acceptance_criteria == ("one", "two")


def test_headings_inside_code_fences_are_ignored() -> None:
    text = "## Real\n\n```\n## Not a requirement\n```\n"

    assert [r.title for r in parse_markdown(text).requirements] == ["Real"]


def test_crlf_input_is_accepted() -> None:
    result = parse_markdown("## R\r\n\r\nPriority: low\r\n\r\nText\r\n")

    assert result.requirements[0].priority == "low"
    assert result.requirements[0].description == "Text"


def test_a_document_without_headings_reports_where_to_start() -> None:
    result = parse_markdown("Just some prose.\n")

    assert result.requirements == []
    assert result.issues[0].message.startswith("no requirement found")


def test_unknown_priority_and_status_are_reported_not_replaced() -> None:
    text = (
        "## A\n\nPriority: urgent\n\n## B\n\nStatus: maybe\n\n## C\n\nPriority: low\n"
    )

    result = parse_markdown(text)

    assert [r.title for r in result.requirements] == ["C"]
    messages = [i.message for i in result.issues]
    assert "priority 'urgent' is not understood; use high, medium, low." in messages
    assert any(m.startswith("status 'maybe' is not understood") for m in messages)
    assert [i.line for i in result.issues] == [1, 5]


def test_an_empty_title_and_a_huge_title_are_rejected() -> None:
    long_title = "x" * 201

    result = parse_markdown(f"## {long_title}\n\ntext\n")

    assert result.requirements == []
    assert "longer than 200" in result.issues[0].message


def test_unknown_key_lines_stay_in_the_description() -> None:
    result = parse_markdown("## R\n\nNote: keep this line\n\nText\n")

    assert result.requirements[0].description == "Note: keep this line\n\nText"


def test_plain_text_blocks_are_requirements() -> None:
    text = (
        "Users can log in\nPriority: high\nThey use e-mail.\n\n"
        "Users can log out\n\n\nUsers can export\nTags: reports\n"
    )

    result = parse_text(text)

    assert [r.title for r in result.requirements] == [
        "Users can log in",
        "Users can log out",
        "Users can export",
    ]
    assert result.requirements[0].priority == "high"
    assert result.requirements[0].description == "They use e-mail."
    assert result.requirements[2].tags == ("reports",)
    assert [r.line for r in result.requirements] == [1, 5, 8]


def test_empty_text_is_reported() -> None:
    result = parse_text("  \n\n")

    assert result.requirements == []
    assert result.issues[0].message == "the text has no requirement."


@pytest.mark.parametrize("priority", ["High", "HIGH", " high ", "alta"])
def test_priority_names_are_case_insensitive(priority: str) -> None:
    result = parse_text(f"Title\nPriority: {priority}\n")

    assert result.requirements[0].priority == "high"


def test_status_with_a_space_is_understood() -> None:
    assert parse_text("T\nStatus: in review\n").requirements[0].status == "in_review"
