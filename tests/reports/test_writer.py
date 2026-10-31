from conftest import make_case, make_requirement
from qa_workbench.executions.recovery import record_correction
from qa_workbench.reports.writer import (
    is_execution_report_stale,
    render_traceability_report,
    report_path,
    write_execution_report,
    write_traceability_report,
)
from qa_workbench.storage.frontmatter import read_document
from qa_workbench.storage.repository import MarkdownRepository


def test_an_execution_report_is_saved_with_frontmatter(
    chain: MarkdownRepository,
) -> None:
    path = write_execution_report(chain, "EXEC-001")

    document = read_document(path)
    assert path == chain.root / "reports" / "EXEC-001.md"
    assert document.metadata["report"] == "execution"
    assert document.metadata["source"] == "EXEC-001"
    assert document.metadata["execution_status"] == "finalized"
    assert len(document.metadata["source_sha256"]) == 64
    assert document.metadata["generated_at"].utcoffset() is not None
    assert document.body.startswith("# Execution report EXEC-001")


def test_a_fresh_report_is_not_stale_and_a_missing_one_is_unknown(
    chain: MarkdownRepository,
) -> None:
    assert is_execution_report_stale(chain, "EXEC-001") is None

    write_execution_report(chain, "EXEC-001")

    assert is_execution_report_stale(chain, "EXEC-001") is False


def test_a_correction_makes_the_saved_report_stale(chain: MarkdownRepository) -> None:
    write_execution_report(chain, "EXEC-001")

    record_correction(chain, "EXEC-001", author="Ana", justification="Wrong version.")

    assert is_execution_report_stale(chain, "EXEC-001") is True


def test_regenerating_a_report_after_a_correction_includes_it(
    chain: MarkdownRepository,
) -> None:
    write_execution_report(chain, "EXEC-001")
    record_correction(chain, "EXEC-001", author="Ana", justification="Wrong version.")

    path = write_execution_report(chain, "EXEC-001")

    assert "Correction recorded by Ana: Wrong version." in path.read_text(
        encoding="utf-8"
    )
    assert is_execution_report_stale(chain, "EXEC-001") is False


def test_a_damaged_saved_report_counts_as_stale(chain: MarkdownRepository) -> None:
    path = write_execution_report(chain, "EXEC-001")
    path.write_text("not a report", encoding="utf-8")

    assert is_execution_report_stale(chain, "EXEC-001") is True


def test_the_report_path_lives_in_the_reports_folder(
    chain: MarkdownRepository,
) -> None:
    assert report_path(chain, "traceability") == (
        chain.root / "reports" / "traceability.md"
    )


def test_the_traceability_report_has_a_summary_a_matrix_and_gaps(
    chain: MarkdownRepository,
) -> None:
    report = render_traceability_report(chain)

    assert "## Summary\n\n- Requirements: 2\n- Passed: 1\n- With failures: 0" in report
    assert "- Not executed: 0\n- Without a test case: 1" in report
    assert (
        "| [[REQ-001]] | Users can log in | [[TC-001]] EXEC-001: passed (finalized) "
        "| passed |"
    ) in report
    assert "| [[REQ-002]] | Users can log out | - | no test case |" in report
    assert "- [[REQ-002]] has no test case." in report


def test_cases_without_a_requirement_are_listed_as_gaps(
    repo: MarkdownRepository,
) -> None:
    make_requirement(repo, "A")
    make_case(repo)

    report = render_traceability_report(repo)

    assert "- [[TC-001]] is not linked to any requirement." in report


def test_a_project_without_gaps_says_so(repo: MarkdownRepository) -> None:
    make_requirement(repo, "A")
    make_case(repo, requirements=["REQ-001"])

    assert "## Gaps\n\nNone found." in render_traceability_report(repo)


def test_table_cells_escape_pipes(repo: MarkdownRepository) -> None:
    make_requirement(repo, "A | B")

    assert "| A \\| B |" in render_traceability_report(repo)


def test_the_report_states_what_it_does_not_cover(chain: MarkdownRepository) -> None:
    report = render_traceability_report(chain)

    assert "Defects and pipelines: no defect or pipeline records exist yet" in report


def test_the_traceability_report_is_saved(chain: MarkdownRepository) -> None:
    path = write_traceability_report(chain)

    document = read_document(path)
    assert document.metadata["report"] == "traceability"
    assert document.body.startswith("# Traceability")


def test_an_empty_project_gives_an_empty_matrix(repo: MarkdownRepository) -> None:
    report = render_traceability_report(repo)

    assert "- Requirements: 0" in report
    assert "None found." in report
