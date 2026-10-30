"""Release analysis from real commits and files (spec 5.13).

Everything in the result comes from data the repository source returned, and
every claim names the commits and files behind it. The rules are simple and
explainable on purpose, not a model's opinion:

* **Areas** are the first two path segments (``src/auth``).
* **Risk** of an area rises with: sensitive names in its paths (auth, payment,
  migration, ...), files changed in three or more commits, source changed with
  no test change in the same release, and very wide commits.
* **Impacted cases** are test cases whose title, objective, or tags contain a
  word taken from a changed path. The matched words are listed, so a person can
  disagree with the match.
* **Suites** are recommended when they contain impacted cases; smoke suites are
  always suggested, and regression suites when any area is high risk.

A word match is a heuristic, not proof of impact, and the result says so.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field

from qa_workbench.integrations.models import Commit, MergeRequest
from qa_workbench.integrations.ports import RepositorySource
from qa_workbench.storage.repository import MarkdownRepository

SENSITIVE = (
    "auth",
    "login",
    "password",
    "session",
    "token",
    "permission",
    "payment",
    "billing",
    "checkout",
    "migration",
    "schema",
    "security",
    "config",
    "crypto",
)
GENERIC = frozenset(
    "src lib app apps test tests spec specs index main init utils util common "
    "core base helpers helper module modules package py js ts tsx jsx md yml yaml "
    "json txt css html java go rs cs rb php".split()
)
HIGH, MEDIUM, LOW = "high", "medium", "low"
_ORDER = {HIGH: 2, MEDIUM: 1, LOW: 0}
CHURN_COMMITS = 3
WIDE_COMMIT_FILES = 20
_SPLIT = re.compile(r"[/_.\-\s]+|(?<=[a-z0-9])(?=[A-Z])")


@dataclass(frozen=True)
class RiskArea:
    area: str
    level: str
    reasons: tuple[str, ...]
    commits: tuple[str, ...]
    files: tuple[str, ...]


@dataclass(frozen=True)
class ImpactedCase:
    case_id: str
    title: str
    matched: tuple[str, ...]


@dataclass(frozen=True)
class SuiteAdvice:
    suite_id: str
    title: str
    why: str


@dataclass(frozen=True)
class ReleaseAnalysis:
    scope: str
    commits: tuple[Commit, ...]
    merge_requests: tuple[MergeRequest, ...]
    areas: tuple[RiskArea, ...]
    impacted_cases: tuple[ImpactedCase, ...]
    suites: tuple[SuiteAdvice, ...]
    regression: str
    justification: tuple[str, ...]
    limitations: tuple[str, ...] = field(default_factory=tuple)

    @property
    def files(self) -> dict[str, list[str]]:
        changed: dict[str, list[str]] = defaultdict(list)
        for commit in self.commits:
            for path in commit.files:
                changed[path].append(commit.sha)
        return dict(changed)

    @property
    def risk_level(self) -> str:
        return max((a.level for a in self.areas), key=_ORDER.__getitem__, default=LOW)


def area_of(path: str) -> str:
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


def is_test_path(path: str) -> bool:
    lowered = path.lower()
    return bool(
        re.search(r"(^|/)(tests?|specs?|__tests__)(/|$)", lowered)
        or re.search(r"(test_|_test\.|\.test\.|\.spec\.)", lowered)
    )


def words_of(path: str) -> set[str]:
    return {
        part.lower()
        for part in _SPLIT.split(path)
        if len(part) >= 3 and part.lower() not in GENERIC and not part.isdigit()
    }


def _risk(
    area: str,
    commits: list[Commit],
    files: list[str],
    all_files: dict[str, set[str]],
    test_words: set[str],
) -> RiskArea:
    reasons: list[str] = []
    sensitive = sorted({w for f in files for w in words_of(f) if w in SENSITIVE})
    if sensitive:
        reasons.append(f"touches sensitive names: {', '.join(sensitive)}")
    churn = sorted(f for f in files if len(all_files[f]) >= CHURN_COMMITS)
    if churn:
        reasons.append(
            f"{len(churn)} file(s) changed in {CHURN_COMMITS} or more commits "
            f"(for example {churn[0]})"
        )
    # Tests usually live in another folder, so "tested" means: some test file
    # changed in this release shares a word with this area's source files.
    source_words = {w for f in files if not is_test_path(f) for w in words_of(f)}
    untested = bool(source_words) and not (source_words & test_words)
    if untested:
        reasons.append("source changed with no test change in this release")
    wide = [c for c in commits if len(c.files) > WIDE_COMMIT_FILES]
    if wide:
        reasons.append(
            f"{len(wide)} commit(s) touch more than {WIDE_COMMIT_FILES} files"
        )
    if len(reasons) >= 2 or (sensitive and untested):
        level = HIGH
    elif reasons:
        level = MEDIUM
    else:
        level = LOW
    return RiskArea(
        area,
        level,
        tuple(reasons),
        tuple(sorted({c.sha for c in commits})),
        tuple(sorted(files)),
    )


def analyze_release(
    source: RepositorySource,
    repository: MarkdownRepository,
    *,
    ref: str | None = None,
    since: str | None = None,
    limit: int = 30,
    merge_requests: bool = True,
) -> ReleaseAnalysis:
    """Read real commits (and merged MRs) and analyze them against the project."""
    listed = source.list_commits(ref=ref, since=since, limit=limit)
    commits = tuple(source.get_commit(c.sha) for c in listed)
    mrs: tuple[MergeRequest, ...] = ()
    if merge_requests:
        mrs = tuple(
            source.get_merge_request(m.iid)
            for m in source.list_merge_requests(state="merged", limit=limit)
        )
    scope = (
        " ".join(
            part
            for part in (f"ref {ref}" if ref else "", f"since {since}" if since else "")
            if part
        )
        or "latest commits"
    )

    by_file: dict[str, set[str]] = defaultdict(set)
    by_area: dict[str, list[Commit]] = defaultdict(list)
    area_files: dict[str, set[str]] = defaultdict(set)
    for commit in commits:
        for path in commit.files:
            by_file[path].add(commit.sha)
            area_files[area_of(path)].add(path)
            if commit not in by_area[area_of(path)]:
                by_area[area_of(path)].append(commit)
    test_words = {w for p in by_file if is_test_path(p) for w in words_of(p)}
    areas = tuple(
        sorted(
            (
                _risk(
                    area, by_area[area], sorted(area_files[area]), by_file, test_words
                )
                for area in area_files
            ),
            key=lambda a: (-_ORDER[a.level], a.area),
        )
    )

    changed_words = {w for path in by_file for w in words_of(path)}
    impacted = _impacted_cases(repository, changed_words)
    suites = _suites(repository, impacted, areas)
    regression, justification = _regression(areas, impacted, suites, commits)
    limitations = [
        "Impact is a word match between changed paths and test cases, not proof.",
        "Risk rules look at paths and commit shapes only; code was not analyzed.",
    ]
    if not commits:
        limitations.append("No commits were found for this scope.")
    elif not any(c.files for c in commits):
        limitations.append("The commits list no changed files.")
    return ReleaseAnalysis(
        scope,
        commits,
        mrs,
        areas,
        impacted,
        suites,
        regression,
        justification,
        tuple(limitations),
    )


def _impacted_cases(
    repository: MarkdownRepository, changed_words: set[str]
) -> tuple[ImpactedCase, ...]:
    found = []
    for case in repository.list_records("TC").records:
        if case.metadata.get("status") == "deprecated":
            continue
        text = " ".join(
            [
                str(case.metadata.get("title", "")),
                str(case.metadata.get("objective", "")),
                " ".join(map(str, case.metadata.get("tags") or [])),
            ]
        ).lower()
        tokens = set(re.findall(r"[a-z0-9]+", text))
        matched = sorted(changed_words & tokens)
        if matched:
            found.append(
                ImpactedCase(case.id, str(case.metadata["title"]), tuple(matched))
            )
    return tuple(found)


def _suites(
    repository: MarkdownRepository,
    impacted: tuple[ImpactedCase, ...],
    areas: tuple[RiskArea, ...],
) -> tuple[SuiteAdvice, ...]:
    impacted_ids = {c.case_id for c in impacted}
    any_high = any(a.level == HIGH for a in areas)
    advice = []
    for suite in repository.list_records("SUITE").records:
        if suite.metadata.get("status") == "archived":
            continue
        members = set(suite.metadata.get("cases") or [])
        hit = sorted(members & impacted_ids)
        kind = suite.metadata.get("type")
        if hit:
            why = f"contains impacted case(s): {', '.join(hit)}"
        elif kind == "smoke":
            why = "smoke suite: run on every release"
        elif kind == "regression" and any_high:
            why = "regression suite: a high-risk area changed"
        else:
            continue
        advice.append(SuiteAdvice(suite.id, str(suite.metadata["title"]), why))
    return tuple(advice)


def _regression(
    areas: tuple[RiskArea, ...],
    impacted: tuple[ImpactedCase, ...],
    suites: tuple[SuiteAdvice, ...],
    commits: tuple[Commit, ...],
) -> tuple[str, tuple[str, ...]]:
    high = [a for a in areas if a.level == HIGH]
    medium = [a for a in areas if a.level == MEDIUM]
    lines = [f"{len(commits)} commit(s) read from the repository."]
    if high:
        regression = (
            "Full regression recommended: "
            f"{len(high)} high-risk area(s) ({', '.join(a.area for a in high)})."
        )
    elif medium or impacted:
        regression = "Run the impacted cases and the smoke suite."
    else:
        regression = "Smoke suite is enough on the evidence available."
    for area in high + medium:
        lines.append(f"{area.area} is {area.level}: {'; '.join(area.reasons)}.")
    if impacted:
        lines.append(f"{len(impacted)} test case(s) match the changed paths.")
    elif areas:
        lines.append("No test case matches the changed paths; coverage may be missing.")
    if suites:
        lines.append(f"{len(suites)} suite(s) recommended.")
    return regression, tuple(lines)
