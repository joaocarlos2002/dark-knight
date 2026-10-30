import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.main import app

runner = CliRunner()


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def isolated_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, _plain(result.output)


@pytest.fixture
def ai_requirements(tmp_path: Path, isolated_data: Path) -> None:
    source = tmp_path / "ai.md"
    source.write_text("## Users can log in\n\n## Users can log out\n", encoding="utf-8")
    assert _run("project", "create", "Demo")[0].exit_code == 0
    result, _ = _run(
        "requirements",
        "import",
        str(source),
        "-p",
        "PROJ-001",
        "--generated-by",
        "opencode",
    )
    assert result.exit_code == 0


def test_ai_imports_are_recorded_as_ai_generated_and_pending(
    ai_requirements: None, isolated_data: Path
) -> None:
    text = (
        isolated_data / "projects" / "PROJ-001" / "requirements" / "REQ-001.md"
    ).read_text(encoding="utf-8")

    result, output = _run("review", "pending", "-p", "PROJ-001")

    assert "origin: ai" in text
    assert "generated_by: opencode" in text
    assert result.exit_code == 0
    assert "REQ-001  draft       opencode      Users can log in" in output
    assert "REQ-002" in output


def test_the_review_path_to_approval(ai_requirements: None) -> None:
    submitted, output = _run("review", "submit", "REQ-001", "-p", "PROJ-001")
    decided, decision = _run(
        "review",
        "decide",
        "REQ-001",
        "-p",
        "PROJ-001",
        "--decision",
        "approved",
        "--reviewer",
        "Ana",
        "--comment",
        "Matches the spec.",
    )
    _, pending = _run("review", "pending", "-p", "PROJ-001")
    _, listing = _run("requirements", "list", "-p", "PROJ-001")

    assert submitted.exit_code == 0
    assert "REQ-001 is now in_review." in output
    assert decided.exit_code == 0
    assert "REQ-001 is now approved." in decision
    assert "REQ-001" not in pending
    assert "REQ-001  approved" in listing


def test_the_generator_cannot_approve(ai_requirements: None) -> None:
    _run("review", "submit", "REQ-001", "-p", "PROJ-001")

    result, output = _run(
        "review",
        "decide",
        "REQ-001",
        "-p",
        "PROJ-001",
        "--decision",
        "approved",
        "--reviewer",
        "opencode",
    )

    assert result.exit_code == 1
    assert "the reviewer must be a different person" in output


def test_changes_requested_returns_the_record_to_draft(ai_requirements: None) -> None:
    _run("review", "submit", "REQ-001", "-p", "PROJ-001")

    result, output = _run(
        "review",
        "decide",
        "REQ-001",
        "-p",
        "PROJ-001",
        "--decision",
        "changes-requested",
        "--reviewer",
        "Ana",
    )

    assert result.exit_code == 0
    assert "REQ-001 is now draft." in output


def test_deciding_before_submitting_is_refused(ai_requirements: None) -> None:
    result, output = _run(
        "review",
        "decide",
        "REQ-001",
        "-p",
        "PROJ-001",
        "--decision",
        "approved",
        "--reviewer",
        "Ana",
    )

    assert result.exit_code == 1
    assert "submit it for review before deciding" in output


def test_an_unknown_decision_is_a_usage_error(ai_requirements: None) -> None:
    _run("review", "submit", "REQ-001", "-p", "PROJ-001")

    result, _ = _run(
        "review",
        "decide",
        "REQ-001",
        "-p",
        "PROJ-001",
        "--decision",
        "maybe",
        "--reviewer",
        "Ana",
    )

    assert result.exit_code == 2


def test_nothing_pending_is_said_plainly() -> None:
    _run("project", "create", "Demo")

    result, output = _run("review", "pending", "-p", "PROJ-001")

    assert result.exit_code == 0
    assert "Nothing is waiting for review." in output


def test_an_ai_source_that_claims_approval_is_not_imported(tmp_path: Path) -> None:
    _run("project", "create", "Demo")
    source = tmp_path / "claims.md"
    source.write_text("## Sneaky\n\nStatus: approved\n", encoding="utf-8")

    result, output = _run(
        "requirements",
        "import",
        str(source),
        "-p",
        "PROJ-001",
        "--generated-by",
        "opencode",
    )

    assert result.exit_code == 1
    assert "cannot be approved without a human review" in output
    assert "0 created" in output


def test_a_human_source_may_state_its_own_status(tmp_path: Path) -> None:
    _run("project", "create", "Demo")
    source = tmp_path / "human.md"
    source.write_text("## Agreed\n\nStatus: approved\n", encoding="utf-8")

    result, _ = _run("requirements", "import", str(source), "-p", "PROJ-001")

    assert result.exit_code == 0
