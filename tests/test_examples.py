"""The examples and the documented first session must keep working."""

import re
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from qa_workbench.api.definition import load_definition
from qa_workbench.main import app
from qa_workbench.requirements.parser import parse_markdown

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("DARK_KNIGHT_DATA_DIR", str(tmp_path / "data"))


def _run(*args: str):
    result = runner.invoke(app, list(args))
    return result, result.output


def test_the_requirements_example_parses_without_problems() -> None:
    parsed = parse_markdown((EXAMPLES / "requirements.md").read_text(encoding="utf-8"))

    assert parsed.issues == []
    assert [r.title for r in parsed.requirements][0] == "Customers can pay by card"
    assert len(parsed.requirements) == 3
    assert all(r.acceptance_criteria for r in parsed.requirements)


def test_the_api_example_is_a_valid_definition_without_credentials() -> None:
    definition = load_definition(EXAMPLES / "api" / "users-api.yaml")

    assert [s.name for s in definition.steps][0] == "service is healthy"
    auth = [s.auth for s in definition.steps if s.auth.kind != "none"]
    assert auth and all(a.env == "API_TOKEN" for a in auth)  # named, never stored
    assert definition.steps[-1].expect.status == (401, 403)


def test_the_first_session_in_the_examples_readme_works() -> None:
    """Runs the commands of the walkthrough, in order, and checks each one."""
    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    first_session = readme.split("## A first session, end to end")[1].split(
        "Then open the workbench"
    )[0]
    block = re.search(r"```bash\n(.*?)```", first_session, re.S).group(1)
    commands = []
    for line in block.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        if commands and commands[-1].endswith("\\"):
            commands[-1] = commands[-1][:-1] + line.strip()
        else:
            commands.append(line.strip())
    assert len(commands) == 8

    for command in commands:
        words = _split(command)
        assert words[0] == "batman", command
        words = [
            str(EXAMPLES / "requirements.md") if w == "examples/requirements.md" else w
            for w in words[1:]
        ]
        result, output = _run(*words)
        assert result.exit_code == 0, f"{command}\n{output}"

    coverage = _run("requirements", "coverage", "-p", "PROJ-001")[1]
    assert "REQ-001" in coverage


def _split(command: str) -> list[str]:
    import shlex

    return shlex.split(command)


def test_the_commands_in_the_integration_snippets_exist() -> None:
    """The safe-integration examples may need servers, but their commands must exist."""
    readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")
    known = {
        ("security", "set"),
        ("api", "run"),
        ("gitlab", "pipelines"),
        ("comments", "draft"),
        ("comments", "publish"),
        ("security", "approve"),
        ("security-tests", "authorize"),
        ("security-tests", "run"),
    }
    used = set(re.findall(r"^batman ([a-z-]+) ([a-z-]+)", readme, re.M))

    assert known <= used
    for group, command in sorted(used - {("project", "create")}):
        result, output = _run(group, command, "--help")
        assert result.exit_code == 0, f"batman {group} {command}\n{output}"


def test_the_readme_links_to_the_examples_and_the_release_guide() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "(examples/README.md)" in readme and "(RELEASING.md)" in readme
    assert tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
