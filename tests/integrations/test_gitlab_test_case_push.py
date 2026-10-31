import json
from pathlib import Path

import pytest
from fake_gitlab import PREFIX, FakeGateway, answer, make_client

from qa_workbench.integrations.gitlab.test_cases import (
    GitLabTestCases,
    merge_description,
    render_description,
    render_sections,
)
from qa_workbench.requirements.schema import REQUIREMENT_SCHEMA
from qa_workbench.security.audit import AuditLog
from qa_workbench.security.guard import ActionGuard, ApprovalRequired
from qa_workbench.security.settings import SecuritySettings
from qa_workbench.storage.repository import MarkdownRepository
from qa_workbench.testcases.builder import Step, TestCaseDraft, create_test_case
from qa_workbench.testcases.gitlab_push import PushError, push_case
from qa_workbench.testcases.schema import TEST_CASE_SCHEMA

WIKI = "https://gitlab.test/groups/nees/-/wikis/Requisitos/GE01.01"
ISSUES = PREFIX + "/issues"


@pytest.fixture
def repo(tmp_path: Path) -> MarkdownRepository:
    repository = MarkdownRepository(
        tmp_path / "project", [REQUIREMENT_SCHEMA, TEST_CASE_SCHEMA]
    )
    repository.create(
        "REQ",
        {
            "title": "GE01.01 Autorizar",
            "status": "draft",
            "source": "GitLab wiki nees",
            "origin": "imported",
            "source_url": WIKI,
            "tags": ["GE01", "GE01.01"],
            "business_rules": ["RN-GE01.01.08"],
        },
        "# GE01.01\n",
    )
    return repository


def _case(repo: MarkdownRepository, **changes) -> str:
    draft = TestCaseDraft(
        title="Autorizar assistente",
        objective="Validar a autorização",
        preconditions=["Gestor logado"],
        steps=[
            Step("Abrir a tela", "A tela abre"),
            Step("Autorizar | ok", "Autorizado"),
        ],
        expected_result="O assistente é autorizado",
        requirements=["REQ-001"],
    )
    for key, value in changes.items():
        setattr(draft, key, value)
    return create_test_case(repo, draft).id


def _guard(tmp_path: Path) -> ActionGuard:
    settings = SecuritySettings(allowed_hosts=("gitlab.test",))
    return ActionGuard(settings, AuditLog(tmp_path / "audit"))


class Remote:
    """A GitLab that records every write and keeps the one case it holds."""

    def __init__(self, existing: dict | None = None) -> None:
        self.writes: list[tuple[str, dict]] = []
        self.case = existing
        self.gateway = FakeGateway({ISSUES: self._issues, ISSUES + "/7": self._one})

    def _issues(self, request):
        if request.body is not None:
            self.writes.append(("POST", request.body))
            self.case = {
                "iid": 7,
                "title": request.body["title"],
                "description": request.body["description"],
                "labels": request.body["labels"].split(","),
                "web_url": "https://gitlab.test/group/app/-/issues/7",
                "state": "opened",
            }
            return answer(self.case, 201)
        return answer([self.case] if self.case else [])

    def _one(self, request):
        if request.body is not None:
            self.writes.append(("PUT", request.body))
            assert self.case is not None
            self.case = {**self.case, "description": request.body["description"]}
        return answer(self.case)

    def remote(self) -> GitLabTestCases:
        return GitLabTestCases(make_client(self.gateway))


def _approve(guard: ActionGuard, error: ApprovalRequired, by: str = "Bea") -> None:
    guard.book.decide(error.request_id, approve=True, by=by)


def _push(repo, guard, remote: Remote, case: str):
    return push_case(repo, case, guard=guard, remote=remote.remote(), actor="Ana")


def test_the_layout_is_the_documented_contract() -> None:
    sections = render_sections(
        objective="Validar",
        preconditions=["Gestor logado", "Escola ativa"],
        steps=[{"action": "Abrir", "expected": "Abre"}, {"action": "Pagar | ok"}],
        expected_result="Pago",
        coverage="RN-GE01.01.08",
        related=[("GE01.01", WIKI)],
    )

    assert render_description("Pagar", sections) == (
        "# Pagar\n\n"
        "## Objetivo\nValidar\n\n"
        "## Pré-condições\n- Gestor logado\n- Escola ativa\n\n"
        "## Passos\n"
        "| Passo | Ação | Resultado Esperado |\n"
        "|-------|------|---------------------|\n"
        "| 1 | Abrir | Abre |\n"
        "| 2 | Pagar \\| ok |  |\n\n"
        "## Resultado Esperado\nPago\n\n"
        "## Critérios/Cobertura\nRN-GE01.01.08\n\n"
        f"## 🔗 Requisitos relacionados\n- GE01.01 — {WIKI}\n"
    )


def test_a_merge_changes_only_the_changed_sections_and_keeps_the_rest() -> None:
    old = render_description(
        "T",
        render_sections(
            objective="A",
            preconditions=[],
            steps=[{"action": "x", "expected": "y"}],
            expected_result="R",
            coverage="",
            related=[],
        ),
    )
    old = old.replace(
        "## Resultado Esperado\nR\n",
        "## Resultado Esperado\nR\n\n## Notas\nfeita à mão\n",
    )
    sections = render_sections(
        objective="A",
        preconditions=[],
        steps=[{"action": "x", "expected": "y"}],
        expected_result="R mudou",
        coverage="",
        related=[("GE01", WIKI)],
    )

    new = merge_description(old, sections)

    assert "R mudou" in new and "feita à mão" in new and "GE01 —" in new
    assert new.startswith(old.split("## Resultado Esperado")[0])  # untouched head
    assert merge_description(new, sections) == new  # a second merge changes nothing


def test_pushing_needs_an_approval_of_this_exact_content(repo, tmp_path) -> None:
    case, guard, remote = _case(repo), _guard(tmp_path), Remote()

    with pytest.raises(ApprovalRequired):
        _push(repo, guard, remote, case)

    assert remote.writes == [] and "gitlab_iid" not in repo.get(case).metadata


def test_an_approved_push_creates_one_test_case_in_the_standard_layout(
    repo, tmp_path
) -> None:
    case, guard, remote = _case(repo), _guard(tmp_path), Remote()
    with pytest.raises(ApprovalRequired) as asked:
        _push(repo, guard, remote, case)
    _approve(guard, asked.value)

    result = _push(repo, guard, remote, case)

    assert result.action == "created" and result.iid == 7
    method, body = remote.writes[0]
    assert method == "POST" and body["issue_type"] == "test_case"
    assert body["labels"] == "GE01,GE01.01,type::testcase"
    assert "## Critérios/Cobertura\nRN-GE01.01.08" in body["description"]
    assert f"- GE01.01 — {WIKI}" in body["description"]
    meta = repo.get(case).metadata
    assert meta["gitlab_iid"] == 7 and len(meta["gitlab_sha256"]) == 64
    assert any(e.kind == "test_case_pushed" for e in guard.audit.entries())


def test_pushing_twice_changes_nothing_the_second_time(repo, tmp_path) -> None:
    case, guard, remote = _case(repo), _guard(tmp_path), Remote()
    with pytest.raises(ApprovalRequired) as asked:
        _push(repo, guard, remote, case)
    _approve(guard, asked.value)
    _push(repo, guard, remote, case)

    again = _push(repo, guard, remote, case)

    assert again.action == "unchanged" and len(remote.writes) == 1


def test_a_changed_case_needs_a_new_approval_and_updates_in_place(
    repo, tmp_path
) -> None:
    case, guard, remote = _case(repo), _guard(tmp_path), Remote()
    with pytest.raises(ApprovalRequired) as first:
        _push(repo, guard, remote, case)
    _approve(guard, first.value)
    _push(repo, guard, remote, case)
    assert remote.case is not None
    remote.case["description"] += "\n## Notas\nfeita à mão\n"
    repo.update(case, {"expected_result": "Resultado novo"})

    with pytest.raises(ApprovalRequired) as second:
        _push(repo, guard, remote, case)
    _approve(guard, second.value)
    result = _push(repo, guard, remote, case)

    assert result.action == "updated" and len(remote.writes) == 2
    method, body = remote.writes[1]
    assert method == "PUT"
    assert "Resultado novo" in body["description"]
    assert "feita à mão" in body["description"]
    assert body["description"].count("## Objetivo") == 1


def test_an_existing_case_with_the_same_title_is_updated_not_copied(
    repo, tmp_path
) -> None:
    case, guard = _case(repo), _guard(tmp_path)
    remote = Remote(
        {
            "iid": 7,
            "title": "Autorizar assistente",
            "description": "# Autorizar assistente\n\n## Objetivo\nantigo\n",
            "labels": ["GE01.01", "type::testcase"],
            "web_url": "https://gitlab.test/group/app/-/issues/7",
            "state": "opened",
        }
    )
    with pytest.raises(ApprovalRequired) as asked:
        _push(repo, guard, remote, case)
    _approve(guard, asked.value)

    result = _push(repo, guard, remote, case)

    assert result.action == "updated"
    assert [method for method, _ in remote.writes] == ["PUT"]
    assert "Validar a autorização" in remote.writes[0][1]["description"]


def test_a_deprecated_case_is_not_pushed_and_a_failure_is_recorded(
    repo, tmp_path
) -> None:
    case, guard = _case(repo), _guard(tmp_path)
    failing = Remote()
    failing.gateway.routes[ISSUES] = lambda r: (
        answer([]) if r.body is None else answer({"message": "boom"}, 500)
    )
    with pytest.raises(ApprovalRequired) as asked:
        _push(repo, guard, failing, case)
    _approve(guard, asked.value)

    with pytest.raises(PushError, match="server failed"):
        _push(repo, guard, failing, case)
    assert "gitlab_iid" not in repo.get(case).metadata
    assert any(e.kind == "test_case_push_failed" for e in guard.audit.entries())

    repo.update(case, {"status": "deprecated"})
    with pytest.raises(PushError, match="deprecated"):
        _push(repo, guard, Remote(), case)


def test_the_requester_cannot_approve_their_own_push(repo, tmp_path) -> None:
    case, guard, remote = _case(repo), _guard(tmp_path), Remote()
    with pytest.raises(ApprovalRequired) as asked:
        _push(repo, guard, remote, case)

    with pytest.raises(Exception, match="cannot also decide"):
        _approve(guard, asked.value, by="Ana")

    assert json.dumps(remote.writes) == "[]"
