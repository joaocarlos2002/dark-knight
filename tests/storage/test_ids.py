import pytest

from qa_workbench.storage.ids import (
    ID_PREFIXES,
    RecordId,
    format_id,
    is_valid_id,
    next_id,
    parse_id,
)


def test_prefixes_follow_the_specification() -> None:
    assert ID_PREFIXES == (
        "PROJ",
        "REQ",
        "ISSUE",
        "TC",
        "EXEC",
        "BUG",
        "SEC",
        "API",
        "REL",
        "EVD",
        "TP",
        "SUITE",
        "PIPE",
        "PIPE-EXEC",
        "COMMENT",
    )


@pytest.mark.parametrize(
    ("value", "prefix", "number"),
    [
        ("TC-001", "TC", 1),
        ("PROJ-042", "PROJ", 42),
        ("EXEC-1000", "EXEC", 1000),
        ("PIPE-EXEC-007", "PIPE-EXEC", 7),
        ("PIPE-018", "PIPE", 18),
    ],
)
def test_valid_ids_are_parsed(value: str, prefix: str, number: int) -> None:
    assert parse_id(value) == RecordId(prefix, number)
    assert str(parse_id(value)) == value


@pytest.mark.parametrize(
    "value",
    ["", "TC", "TC-", "tc-001", "TC_001", "TC-abc", "TC-001-", "-001", "TC 001"],
)
def test_malformed_ids_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="is not an id"):
        parse_id(value)


def test_unknown_prefix_lists_the_valid_ones() -> None:
    with pytest.raises(ValueError, match="unknown prefix 'FOO'") as error:
        parse_id("FOO-001")

    assert "PIPE-EXEC" in str(error.value)


@pytest.mark.parametrize("value", ["TC-000", "TC-1", "TC-01", "TC-0001"])
def test_non_canonical_numbers_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="not canonical|not an id"):
        parse_id(value)


@pytest.mark.parametrize("value", [None, 1, ["TC-001"], b"TC-001"])
def test_non_strings_are_not_valid_ids(value: object) -> None:
    assert not is_valid_id(value)


def test_format_id_pads_to_three_digits() -> None:
    assert format_id("TC", 7) == "TC-007"
    assert format_id("TC", 1234) == "TC-1234"


def test_format_id_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="Unknown id prefix"):
        format_id("NOPE", 1)
    with pytest.raises(ValueError, match="start at 1"):
        format_id("TC", 0)


def test_next_id_starts_at_one() -> None:
    assert next_id("TC", []) == "TC-001"


def test_next_id_ignores_other_prefixes_and_malformed_values() -> None:
    existing = ["TC-001", "REQ-009", "garbage", "TC-oops", "TC-003"]

    assert next_id("TC", existing) == "TC-004"
    assert next_id("REQ", existing) == "REQ-010"


def test_next_id_never_reuses_a_gap() -> None:
    assert next_id("TC", ["TC-001", "TC-005"]) == "TC-006"


def test_pipeline_prefixes_do_not_collide() -> None:
    assert next_id("PIPE", ["PIPE-EXEC-009", "PIPE-002"]) == "PIPE-003"
    assert next_id("PIPE-EXEC", ["PIPE-EXEC-009", "PIPE-002"]) == "PIPE-EXEC-010"
