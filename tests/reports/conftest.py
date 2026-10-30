"""A small project with the whole chain, from requirement to evidence."""

from pathlib import Path

import pytest

from qa_workbench.executions.recording import finish_step, start_step
from qa_workbench.executions.service import create_execution, move
from qa_workbench.plans.builder import PlanDraft, create_plan, set_selection
from qa_workbench.storage.evidence import EvidenceStore
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.suites.service import create_suite
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.workspace import all_schemas


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    return MarkdownRepository(tmp_path / "project", all_schemas())


def make_requirement(repo: MarkdownRepository, title: str):
    return repo.create(
        "REQ",
        {"title": title, "status": "approved", "source": "spec.md", "origin": "manual"},
        "# " + title + "\n",
    )


def make_case(repo: MarkdownRepository, title: str = "Log in", **overrides: object):
    values = {
        "title": title,
        "objective": "Validate that a registered user can sign in.",
        "preconditions": ["The application is available"],
        "steps": [Step("Open the login page"), Step("Submit valid credentials")],
        "expected_result": "The user reaches the dashboard.",
        **overrides,
    }
    return create_test_case(repo, TestCaseDraft(**values), status="active")


def make_evidence(repo: MarkdownRepository, tmp_path: Path, name: str = "shot.png"):
    file = tmp_path / name
    file.write_bytes(b"png bytes")
    return EvidenceStore(repo).register(
        file, source="playwright", description="Dashboard after login"
    )


def run_execution(repo: MarkdownRepository, **overrides: object):
    values = {
        "execution_type": "manual",
        "executor": "Ana",
        "environment": "staging",
        "test_case": "TC-001",
        "version": "1.4.0",
        **overrides,
    }
    record = create_execution(repo, **values)
    move(repo, record.id, "planned")
    return move(repo, record.id, "running")


def pass_execution(repo: MarkdownRepository, execution_id: str, evidence_id: str):
    start_step(repo, execution_id, 1, "Open the login page")
    finish_step(repo, execution_id, 1, "passed", observed="The form is shown")
    move(
        repo,
        execution_id,
        "passed",
        observed_result="The dashboard is shown.",
        evidence=[evidence_id],
    )
    return move(repo, execution_id, "finalized")


@pytest.fixture
def chain(repo: MarkdownRepository, tmp_path: Path):
    """REQ-001 -> TC-001 -> SUITE-001 -> TP-001 -> EXEC-001 -> EVD-001."""
    make_requirement(repo, "Users can log in")
    make_requirement(repo, "Users can log out")
    make_case(repo, requirements=["REQ-001"])
    create_suite(repo, "Smoke", "smoke", cases=["TC-001"])
    plan = create_plan(
        repo,
        PlanDraft(
            title="Release 1.4",
            scope="s",
            strategy="s",
            objectives=["o"],
            entry_criteria=["e"],
            exit_criteria=["x"],
            suites=["SUITE-001"],
        ),
    )
    set_selection(
        repo,
        plan.id,
        [
            {
                "id": "TC-001",
                "decision": "include",
                "reasons": [{"factor": "criticality", "detail": "marked high"}],
            }
        ],
    )
    evidence = make_evidence(repo, tmp_path)
    execution = run_execution(repo, plan="TP-001", suite="SUITE-001")
    pass_execution(repo, execution.id, evidence.id)
    return repo
