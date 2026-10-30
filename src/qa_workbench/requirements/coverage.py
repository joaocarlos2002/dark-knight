"""Requirement coverage (REQ-010).

A requirement is covered when at least one test case is related to it. The
relation can be written on either side: the requirement lists the case in
``cases``, or the case lists the requirement in ``requirements``.
"""

from dataclasses import dataclass

from qa_workbench.storage.repository import MarkdownRepository


@dataclass(frozen=True)
class RequirementCoverage:
    """Coverage of one requirement."""

    id: str
    title: str
    status: str
    cases: tuple[str, ...]
    missing_cases: tuple[str, ...]

    @property
    def covered(self) -> bool:
        return bool(self.cases)


def coverage(repository: MarkdownRepository) -> list[RequirementCoverage]:
    """Coverage of every requirement, ordered by id.

    ``missing_cases`` lists cases named by a requirement that do not exist. It
    can only be checked when the repository knows test cases; otherwise it is
    empty and nothing is claimed about them.
    """
    knows_cases = "TC" in repository.prefixes
    existing: set[str] = set(repository.record_ids("TC")) if knows_cases else set()
    reverse: dict[str, set[str]] = {}
    if knows_cases:
        for case in repository.list_records("TC").records:
            for requirement_id in case.metadata.get("requirements") or []:
                reverse.setdefault(requirement_id, set()).add(case.id)

    report: list[RequirementCoverage] = []
    for requirement in repository.list_records("REQ").records:
        declared = set(requirement.metadata.get("cases") or [])
        missing = sorted(declared - existing) if knows_cases else []
        related = (declared & existing if knows_cases else declared) | reverse.get(
            requirement.id, set()
        )
        report.append(
            RequirementCoverage(
                id=requirement.id,
                title=requirement.metadata["title"],
                status=requirement.metadata["status"],
                cases=tuple(sorted(related)),
                missing_cases=tuple(missing),
            )
        )
    return report
