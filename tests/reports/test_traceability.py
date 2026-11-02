from pathlib import Path

import pytest

from conftest import (
    make_case,
    make_evidence,
    make_requirement,
    pass_execution,
    run_execution,
)
from qa_workbench.executions.service import move
from qa_workbench.reports.traceability import build_graph, matrix, trace
from qa_workbench.storage.repository import MarkdownRepository


def test_the_whole_chain_is_found_downstream_of_a_requirement(
    chain: MarkdownRepository,
) -> None:
    result = trace(build_graph(chain), "REQ-001")

    assert result.upstream == {}
    assert result.downstream == {
        "TC": ("TC-001",),
        "SUITE": ("SUITE-001",),
        "TP": ("TP-001",),
        "EXEC": ("EXEC-001",),
        "EVD": ("EVD-001",),
    }


def test_the_whole_chain_is_found_upstream_of_an_execution(
    chain: MarkdownRepository,
) -> None:
    result = trace(build_graph(chain), "EXEC-001")

    assert result.upstream == {
        "REQ": ("REQ-001",),
        "TC": ("TC-001",),
        "SUITE": ("SUITE-001",),
        "TP": ("TP-001",),
    }
    assert result.downstream == {"EVD": ("EVD-001",)}


def test_unrelated_requirements_are_not_dragged_in(chain: MarkdownRepository) -> None:
    result = trace(build_graph(chain), "EXEC-001")

    assert "REQ-002" not in result.upstream["REQ"]
    assert trace(build_graph(chain), "REQ-002").downstream == {}


def test_two_requirements_sharing_a_case_do_not_see_each_other(
    repo: MarkdownRepository,
) -> None:
    make_requirement(repo, "A")
    make_requirement(repo, "B")
    make_case(repo, requirements=["REQ-001", "REQ-002"])

    result = trace(build_graph(repo), "REQ-001")

    assert result.downstream == {"TC": ("TC-001",)}
    assert trace(build_graph(repo), "TC-001").upstream == {
        "REQ": ("REQ-001", "REQ-002")
    }


def test_links_declared_on_either_side_are_found(repo: MarkdownRepository) -> None:
    case = make_case(repo)
    repo.create(
        "REQ",
        {
            "title": "R",
            "status": "approved",
            "source": "x",
            "origin": "manual",
            "cases": [case.id],
        },
    )

    assert trace(build_graph(repo), "REQ-001").downstream == {"TC": ("TC-001",)}


def test_a_defect_that_is_not_stored_still_shows_up_but_does_not_exist(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    make_case(repo)
    run_execution(repo)
    move(
        repo,
        "EXEC-001",
        "failed",
        observed_result="Error 500",
        failure_type="product",
        bugs=["BUG-001"],
    )

    graph = build_graph(repo)

    assert trace(graph, "EXEC-001").downstream == {"BUG": ("BUG-001",)}
    assert graph.exists("EXEC-001")
    assert not graph.exists("BUG-001")


def test_an_invalid_id_is_refused(chain: MarkdownRepository) -> None:
    with pytest.raises(ValueError):
        trace(build_graph(chain), "nope")


def test_the_matrix_shows_status_per_requirement(chain: MarkdownRepository) -> None:
    rows = {row.requirement: row for row in matrix(chain)}

    assert rows["REQ-001"].cases == (("TC-001", "EXEC-001: passed (finalized)"),)
    assert rows["REQ-001"].flag == "passed"
    assert rows["REQ-002"].cases == ()
    assert rows["REQ-002"].flag == "no test case"


def test_a_requirement_whose_case_was_never_run_is_flagged(
    repo: MarkdownRepository,
) -> None:
    make_requirement(repo, "A")
    make_case(repo, requirements=["REQ-001"])

    (row,) = matrix(repo)

    assert row.cases == (("TC-001", "not executed"),)
    assert row.flag == "not executed"


def test_the_latest_execution_is_the_one_that_counts(
    chain: MarkdownRepository, tmp_path: Path
) -> None:
    run_execution(chain)
    move(
        chain,
        "EXEC-002",
        "failed",
        observed_result="Regression",
        failure_type="product",
    )

    row = next(r for r in matrix(chain) if r.requirement == "REQ-001")

    assert row.cases == (("TC-001", "EXEC-002: failed"),)
    assert row.flag == "has failures"


def test_an_execution_still_running_is_in_progress(
    repo: MarkdownRepository, tmp_path: Path
) -> None:
    make_requirement(repo, "A")
    make_case(repo, requirements=["REQ-001"])
    run_execution(repo)

    (row,) = matrix(repo)

    assert row.flag == "in progress or inconclusive"


def test_a_pass_after_a_failure_is_judged_by_the_latest(
    chain: MarkdownRepository, tmp_path: Path
) -> None:
    run_execution(chain)
    move(
        chain,
        "EXEC-002",
        "failed",
        observed_result="x",
        failure_type="test",
    )
    evidence = make_evidence(chain, tmp_path, "again.png")
    run_execution(chain)
    pass_execution(chain, "EXEC-003", evidence.id)

    row = next(r for r in matrix(chain) if r.requirement == "REQ-001")

    assert row.flag == "passed"
