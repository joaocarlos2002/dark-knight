from pathlib import Path

from conftest import make_case, make_evidence, pass_execution, run_execution
from qa_workbench.executions.recording import (
    check_preconditions,
    finish_step,
    start_step,
)
from qa_workbench.executions.recovery import record_correction, recover
from qa_workbench.executions.service import create_execution, move
from qa_workbench.reports.execution import render_execution_report
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.workspace import all_schemas

SECTIONS = [
    "# Execution report EXEC-001",
    "## Identification",
    "## Objective",
    "## Environment",
    "## Preconditions",
    "## Procedure",
    "## Expected result",
    "## Observed result",
    "## Status",
    "## Evidence",
    "## Conclusion",
    "## Limitations",
    "## Traceability",
]


def _section(report: str, title: str) -> str:
    start = report.index(f"## {title}\n") + len(f"## {title}\n")
    end = report.find("\n## ", start)
    return report[start : end if end != -1 else len(report)].strip()


def test_the_report_has_the_sections_of_the_specification_in_order(
    chain: MarkdownRepository,
) -> None:
    report = render_execution_report(chain, "EXEC-001")

    positions = [report.index(heading) for heading in SECTIONS]
    assert positions == sorted(positions)


def test_identification_links_the_records_it_belongs_to(
    chain: MarkdownRepository,
) -> None:
    section = _section(render_execution_report(chain, "EXEC-001"), "Identification")

    assert "- Execution: EXEC-001" in section
    assert "- Type: manual" in section
    assert "- Executor: Ana" in section
    assert "- Test case: [[TC-001]] Log in" in section
    assert "- Plan: [[TP-001]]" in section
    assert "- Suite: [[SUITE-001]]" in section


def test_objective_and_environment_come_from_the_records(
    chain: MarkdownRepository,
) -> None:
    report = render_execution_report(chain, "EXEC-001")

    assert "Validate that a registered user can sign in." in _section(
        report, "Objective"
    )
    assert _section(report, "Environment") == (
        "- Environment: staging\n- Version: 1.4.0"
    )


def test_the_procedure_lists_the_steps_that_were_actually_recorded(
    chain: MarkdownRepository,
) -> None:
    section = _section(render_execution_report(chain, "EXEC-001"), "Procedure")

    assert section == "1. Open the login page - passed (The form is shown)"


def test_expected_and_observed_results_are_the_recorded_ones(
    chain: MarkdownRepository,
) -> None:
    report = render_execution_report(chain, "EXEC-001")

    assert _section(report, "Expected result") == "The user reaches the dashboard."
    assert _section(report, "Observed result") == "The dashboard is shown."


def test_status_uses_a_symbol_and_a_name_and_the_times(
    chain: MarkdownRepository,
) -> None:
    status = _section(render_execution_report(chain, "EXEC-001"), "Status")

    assert status.startswith("✓ PASSED")
    assert "Started: " in status and "Finished: " in status and "Duration: " in status


def test_evidence_shows_its_hash_source_and_integrity(
    chain: MarkdownRepository,
) -> None:
    section = _section(render_execution_report(chain, "EXEC-001"), "Evidence")

    assert section.startswith(
        "- [[EVD-001]] Dashboard after login - playwright, sha256 "
    )
    assert "9 bytes, integrity verified" in section


def test_a_clean_finalized_pass_has_no_known_limitations(
    chain: MarkdownRepository,
) -> None:
    report = render_execution_report(chain, "EXEC-001")

    assert _section(report, "Limitations") == "None known."
    assert _section(report, "Conclusion") == (
        "The execution passed, with 1 evidence item(s) recorded."
    )


def test_traceability_lists_the_chain_around_the_execution(
    chain: MarkdownRepository,
) -> None:
    section = _section(render_execution_report(chain, "EXEC-001"), "Traceability")

    assert "- Upstream REQ: [[REQ-001]]" in section
    assert "- Upstream TC: [[TC-001]]" in section
    assert "- Upstream TP: [[TP-001]]" in section
    assert "- Downstream EVD: [[EVD-001]]" in section


def test_modified_evidence_is_called_out_not_hidden(
    chain: MarkdownRepository,
) -> None:
    stored = chain.root / "evidence" / "files" / "EVD-001" / "shot.png"
    stored.write_bytes(b"tampered")

    report = render_execution_report(chain, "EXEC-001")

    assert "INTEGRITY PROBLEM" in _section(report, "Evidence")
    assert "EVD-001: the file content does not match" in _section(report, "Limitations")


def test_a_failure_states_what_kind_it_was(repo: MarkdownRepository) -> None:
    make_case(repo)
    run_execution(repo)
    move(
        repo,
        "EXEC-001",
        "failed",
        observed_result="Error 500 on submit",
        failure_type="infrastructure",
    )

    report = render_execution_report(repo, "EXEC-001")

    assert _section(report, "Conclusion") == (
        "The execution failed. Observed: Error 500 on submit"
    )
    limitations = _section(report, "Limitations")
    assert "an infrastructure failure, which says nothing about the product" in (
        limitations
    )
    assert "No evidence was collected." in limitations
    assert "The steps were not recorded one by one." in limitations
    assert "not finalized" in limitations
    assert _section(report, "Status").startswith("✗ FAILED")


def test_steps_that_were_not_recorded_fall_back_to_what_the_case_defines(
    repo: MarkdownRepository,
) -> None:
    make_case(repo)
    run_execution(repo)

    procedure = _section(render_execution_report(repo, "EXEC-001"), "Procedure")

    assert procedure.startswith("Steps were not recorded one by one. The case defines:")
    assert "1. Open the login page" in procedure


def test_blocked_and_cancelled_show_their_reason(repo: MarkdownRepository) -> None:
    make_case(repo)
    run_execution(repo)
    move(repo, "EXEC-001", "blocked", reason="Staging was down")
    create_execution(
        repo,
        execution_type="manual",
        executor="Ana",
        environment="staging",
        test_case="TC-001",
    )
    move(repo, "EXEC-002", "cancelled", reason="Superseded")

    blocked = render_execution_report(repo, "EXEC-001")
    cancelled = render_execution_report(repo, "EXEC-002")

    assert _section(blocked, "Conclusion") == (
        "The execution is blocked. Reason: Staging was down"
    )
    assert _section(blocked, "Status").startswith("⊘ BLOCKED")
    assert _section(cancelled, "Conclusion") == (
        "The execution is cancelled. Reason: Superseded"
    )
    assert _section(cancelled, "Status").startswith("■ CANCELLED")


def test_a_running_execution_claims_no_conclusion(repo: MarkdownRepository) -> None:
    make_case(repo)
    run_execution(repo)

    report = render_execution_report(repo, "EXEC-001")

    assert _section(report, "Conclusion") == (
        "No conclusion yet: the execution is running."
    )
    assert _section(report, "Status").startswith("● RUNNING")
    assert "The execution is running, not finalized; this report may change." in (
        _section(report, "Limitations")
    )


def test_a_planned_execution_is_pending(repo: MarkdownRepository) -> None:
    make_case(repo)
    create_execution(
        repo,
        execution_type="manual",
        executor="Ana",
        environment="staging",
        test_case="TC-001",
    )

    status = _section(render_execution_report(repo, "EXEC-001"), "Status")

    assert status.startswith("◷ PENDING (created)")


def test_preconditions_say_what_was_met_and_what_was_not_verified(
    repo: MarkdownRepository,
) -> None:
    make_case(repo, preconditions=["App is up", "Test user exists"])
    run_execution(repo)
    check_preconditions(repo, "EXEC-001", [("App is up", True)])

    section = _section(render_execution_report(repo, "EXEC-001"), "Preconditions")

    assert section == "- Met: App is up\n- Not verified: Test user exists"


def test_an_unmet_precondition_is_not_glossed_over(repo: MarkdownRepository) -> None:
    make_case(repo)
    run_execution(repo)
    check_preconditions(repo, "EXEC-001", [("Test user exists", False)])

    section = _section(render_execution_report(repo, "EXEC-001"), "Preconditions")

    assert "- NOT met: Test user exists" in section


def test_interruptions_and_recoveries_are_reported(repo: MarkdownRepository) -> None:
    make_case(repo)
    run_execution(repo)
    start_step(repo, "EXEC-001", 1, "Submit")
    recover(repo, "EXEC-001", action="resume", note="Laptop slept")
    start_step(repo, "EXEC-001", 2, "Submit again")
    finish_step(repo, "EXEC-001", 2, "passed")

    limitations = _section(render_execution_report(repo, "EXEC-001"), "Limitations")

    assert "Step(s) 1 were interrupted and not observed." in limitations
    assert "Recovered after an interruption (resume): Laptop slept" in limitations


def test_corrections_after_finalization_appear_in_the_report(
    chain: MarkdownRepository,
) -> None:
    record_correction(
        chain,
        "EXEC-001",
        author="Ana",
        justification="Version was 1.4.1, not 1.4.0.",
    )

    limitations = _section(render_execution_report(chain, "EXEC-001"), "Limitations")

    assert "Correction recorded by Ana: Version was 1.4.1, not 1.4.0." in limitations


def test_a_tampered_finalized_execution_is_reported(
    chain: MarkdownRepository,
) -> None:
    path = chain.path_of("EXEC-001")
    path.write_text(
        path.read_text(encoding="utf-8").replace("staging", "production"),
        encoding="utf-8",
    )

    limitations = _section(render_execution_report(chain, "EXEC-001"), "Limitations")

    assert "Integrity: the record was modified after it was finalized" in limitations


def test_an_exploratory_session_without_a_case_is_still_reported(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    create_execution(
        repo,
        execution_type="exploratory",
        executor="Ana",
        environment="staging",
    )
    move(repo, "EXEC-001", "planned")
    move(repo, "EXEC-001", "running")
    evidence = make_evidence(repo, tmp_path)
    move(
        repo,
        "EXEC-001",
        "passed",
        observed_result="No problems found in the checkout area.",
        evidence=[evidence.id],
    )

    report = render_execution_report(repo, "EXEC-001")

    assert "No test case is linked (exploratory session)." in _section(
        report, "Objective"
    )
    assert "Test case:" not in _section(report, "Identification")


def test_the_machine_run_names_its_tool(repo: MarkdownRepository) -> None:
    make_case(repo)
    create_execution(
        repo,
        execution_type="agent_driven",
        executor="alfred",
        environment="staging",
        test_case="TC-001",
        automation_tool="playwright",
    )

    identification = _section(
        render_execution_report(repo, "EXEC-001"), "Identification"
    )

    assert "- Type: agent driven" in identification
    assert "- Automation tool: playwright" in identification


def _failed_with_bug(repo: MarkdownRepository) -> str:
    make_case(repo)
    run_execution(repo)
    move(
        repo,
        "EXEC-001",
        "failed",
        observed_result="Error 500",
        failure_type="product",
        bugs=["BUG-007"],
    )
    return _section(render_execution_report(repo, "EXEC-001"), "Traceability")


def test_defects_without_a_record_schema_are_said_not_to_be_stored(
    tmp_path: Path,
) -> None:
    schemas = [s for s in all_schemas() if s.prefix != "BUG"]
    older = MarkdownRepository(tmp_path / "older", schemas)

    traceability = _failed_with_bug(older)

    assert "Defects: BUG-007 (referenced; defect records are not stored yet)" in (
        traceability
    )


def test_a_referenced_defect_without_a_record_is_reported_as_missing(
    repo: MarkdownRepository,
) -> None:
    traceability = _failed_with_bug(repo)

    assert "Defects: BUG-007 (referenced; no such defect record was found)" in (
        traceability
    )


def test_passed_executions_keep_working_with_the_helper(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    make_case(repo)
    evidence = make_evidence(repo, tmp_path)
    run_execution(repo)
    pass_execution(repo, "EXEC-001", evidence.id)

    assert "✓ PASSED" in render_execution_report(repo, "EXEC-001")
