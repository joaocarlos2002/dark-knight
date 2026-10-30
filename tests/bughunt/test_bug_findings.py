import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.bughunt.schema import BUG_SCHEMA
from qa_workbench.bughunt.service import BugError, reclassify, record_finding
from qa_workbench.main import app
from qa_workbench.storage.errors import RecordValidationError
from qa_workbench.storage.evidence import EVIDENCE_SCHEMA, EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository

runner = CliRunner()


@pytest.fixture
def repository(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "p", [EVIDENCE_SCHEMA, BUG_SCHEMA])


@pytest.fixture
def evidence_id(repository: MarkdownRepository, tmp_path: Path) -> str:
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"png")
    return (
        EvidenceStore(repository)
        .register(shot, source="manual", description="500 page")
        .id
    )


def _finding(repository, evidence_id, **overrides):
    fields = dict(
        title="Checkout returns 500",
        environment="staging 1.4.2",
        found_by="Ana",
        classification="reproduced",
        steps=["Add item", "Press Pay"],
        expected="Order confirmation",
        observed="HTTP 500 page",
        evidence=[evidence_id],
        attempts=3,
        reproductions=3,
    )
    return record_finding(repository, **{**fields, **overrides})


def test_a_proven_defect_can_be_reproduced_and_is_rendered(
    repository, evidence_id
) -> None:
    record = _finding(repository, evidence_id)

    assert record.metadata["status"] == "reproduced"
    assert "Reproduced:** 3 of 3 attempts" in record.body
    assert "## Steps to reproduce" in record.body and evidence_id in record.body


def test_suspicion_needs_no_proof_and_is_the_default(repository) -> None:
    record = record_finding(
        repository, title="Odd flicker", environment="dev", found_by="Ana"
    )

    assert record.metadata["status"] == "suspected"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"evidence": []}, "at least one evidence"),
        ({"steps": []}, "steps to reproduce"),
        ({"expected": ""}, "expected and observed"),
        ({"observed": ""}, "expected and observed"),
        ({"reproductions": 1}, "at least 2"),
        ({"reproductions": 5, "attempts": 3}, "more than attempts"),
    ],
)
def test_a_defect_is_never_confirmed_without_enough_evidence(
    repository, evidence_id, override, message
) -> None:
    with pytest.raises(BugError, match=message):
        _finding(repository, evidence_id, **override)
    assert repository.record_ids("BUG") == []


def test_false_positive_and_environment_problems_need_their_explanation(
    repository,
) -> None:
    with pytest.raises(BugError, match="reason it is one"):
        record_finding(
            repository, title="t", environment="e", found_by="a",
            classification="false_positive",
        )  # fmt: skip
    with pytest.raises(BugError, match="what failed"):
        record_finding(
            repository, title="t", environment="e", found_by="a",
            classification="environment_unavailable",
        )  # fmt: skip
    ok = record_finding(
        repository, title="t", environment="e", found_by="a",
        classification="false_positive", reason="expected behaviour per REQ-004",
    )  # fmt: skip
    assert ok.metadata["status"] == "false_positive"


def test_unknown_classification_secrets_and_bad_evidence_are_refused(
    repository, evidence_id
) -> None:
    with pytest.raises(BugError, match="classification must be one of"):
        _finding(repository, evidence_id, classification="confirmed")
    with pytest.raises(BugError, match="password"):
        _finding(repository, evidence_id, observed="login with password=hunter22")
    with pytest.raises(BugError, match="EVD-404"):
        _finding(repository, evidence_id, evidence=["EVD-404"])
    EvidenceStore(repository).file_path(repository.get(evidence_id)).write_bytes(b"x!")
    with pytest.raises(BugError, match="not usable"):
        _finding(repository, evidence_id)


def test_reclassifying_keeps_who_when_and_why_and_rechecks_the_rules(
    repository, evidence_id
) -> None:
    bug = _finding(
        repository, evidence_id, classification="suspected", attempts=1, reproductions=1
    )

    with pytest.raises(BugError, match="at least 2"):
        reclassify(repository, bug.id, "reproduced", by="Ana", justification="saw it")

    promoted = reclassify(
        repository, bug.id, "reproduced", by="Ana", justification="saw it twice more",
        attempts=3, reproductions=3,
    )  # fmt: skip
    history = promoted.metadata["classification_history"]
    assert history[0]["from"] == "suspected" and history[0]["to"] == "reproduced"
    assert history[0]["by"] == "Ana" and "twice more" in history[0]["why"]
    assert "**Classification:** reproduced" in promoted.body

    with pytest.raises(BugError, match="who is doing it"):
        reclassify(repository, bug.id, "inconclusive", by="", justification="")


def test_a_hand_edited_confirmed_defect_without_proof_fails_on_read(
    repository, evidence_id
) -> None:
    bug = _finding(repository, evidence_id)
    text = bug.path.read_text(encoding="utf-8").replace(
        "reproductions: 3", "reproductions: 0"
    )
    bug.path.write_text(text, encoding="utf-8")

    with pytest.raises(RecordValidationError, match="at least 2"):
        repository.get(bug.id)


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_commands_record_list_reclassify_and_refuse(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "d"))
    run = lambda *a: (lambda r: (r, _plain(r.output)))(runner.invoke(app, list(a)))  # noqa: E731
    run("project", "create", "Demo")

    refused, out = run(
        "bugs", "record", "Checkout 500", "-p", "PROJ-001", "--environment", "staging",
        "--found-by", "Ana", "--classification", "reproduced",
    )  # fmt: skip
    assert refused.exit_code == 1 and "needs at least one evidence" in out

    ok, out = run(
        "bugs", "record", "Odd flicker", "-p", "PROJ-001", "--environment", "staging",
        "--found-by", "Ana",
    )  # fmt: skip
    assert ok.exit_code == 0 and "BUG-001 as suspected" in out
    assert "suspected" in run("bugs", "list", "-p", "PROJ-001")[1]
    assert (
        "No findings"
        in run("bugs", "list", "-p", "PROJ-001", "--classification", "inconclusive")[1]
    )

    done, out = run(
        "bugs", "reclassify", "BUG-001", "inconclusive", "-p", "PROJ-001",
        "--by", "Ana", "--why", "could not repeat",
    )  # fmt: skip
    assert done.exit_code == 0 and "now inconclusive" in out
    assert "Odd flicker" in run("bugs", "show", "BUG-001", "-p", "PROJ-001")[1]
    assert run("bugs", "show", "BUG-009", "-p", "PROJ-001")[0].exit_code == 1
