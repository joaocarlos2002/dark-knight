import ast
import asyncio
import re
from pathlib import Path

import pytest
from textual.widgets import OptionList, Static
from typer.testing import CliRunner

from qa_workbench import i18n
from qa_workbench.core.config import AppConfig, ConfigurationError
from qa_workbench.i18n.pt_br import PT_BR
from qa_workbench.main import app as cli
from qa_workbench.projects.repository import ProjectRepository
from qa_workbench.tui import navigation
from qa_workbench.tui.app import WorkbenchApp
from qa_workbench.tui.components.choice import ChoiceDialog
from qa_workbench.tui.keymap import Keymap

SRC = Path(i18n.__file__).parents[1]
FIELDS = re.compile(r"\{(\w+)\}")
runner = CliRunner()


def _literals(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _sources() -> dict[Path, ast.AST]:
    return {
        path: ast.parse(path.read_text(encoding="utf-8"))
        for path in SRC.rglob("*.py")
        if path.name != "pt_br.py"
    }


def test_a_missing_translation_shows_the_english_text() -> None:
    i18n.set_language("pt-BR")

    assert i18n.tr("Projects") == "Projetos"
    assert i18n.tr("A text nobody translated") == "A text nobody translated"
    assert i18n.tr("Go to {place}", place="X") == "Ir para X"


def test_english_is_the_default_and_returns_the_source() -> None:
    assert i18n.language() == "en" and i18n.tr("Projects") == "Projects"


def test_an_unknown_language_is_a_clear_error() -> None:
    with pytest.raises(i18n.UnknownLanguageError, match="available in: en, pt-BR"):
        i18n.set_language("klingon")


def test_the_code_is_accepted_in_any_case() -> None:
    assert i18n.normalize("PT_br") == "pt-BR"


def test_every_tr_call_with_a_text_has_a_translation() -> None:
    missing = []
    for path, tree in _sources().items():
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value not in PT_BR
            ):
                missing.append(f"{path.name}: {node.args[0].value!r}")

    assert not missing, "\n".join(missing)


def test_every_translation_is_used_by_the_code() -> None:
    used = set().union(*(_literals(tree) for tree in _sources().values()))

    assert not [key for key in PT_BR if key not in used]


def test_a_translation_keeps_the_fields_of_its_source() -> None:
    wrong = [
        k for k, v in PT_BR.items() if set(FIELDS.findall(k)) != set(FIELDS.findall(v))
    ]

    assert not wrong


def test_the_menu_and_the_shortcuts_are_all_translated() -> None:
    texts = [section.title for section in navigation.SECTIONS]
    texts += [item.title for item in navigation.all_items()]
    for shortcut in Keymap.default().shortcuts:
        texts += [shortcut.label, shortcut.description]

    assert [t for t in texts if t not in PT_BR] == []


def test_the_language_is_kept_and_the_environment_wins(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("DARK_KNIGHT_LANGUAGE", raising=False)
    assert AppConfig.load().language == "en"

    result = runner.invoke(cli, ["config", "language", "set", "pt-BR"])
    assert result.exit_code == 0 and AppConfig.load().language == "pt-BR"

    monkeypatch.setenv("DARK_KNIGHT_LANGUAGE", "en")
    assert AppConfig.load().language == "en"


def test_an_unknown_language_in_the_environment_is_refused(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("DARK_KNIGHT_LANGUAGE", "xx")

    with pytest.raises(ConfigurationError, match="DARK_KNIGHT_LANGUAGE"):
        AppConfig.load()


def test_the_command_rejects_an_unknown_language(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path))

    result = runner.invoke(cli, ["config", "language", "set", "xx"])

    assert result.exit_code == 1 and "Unknown language" in result.output


def _run(tmp_path: Path, monkeypatch, scenario) -> None:
    monkeypatch.setenv("DARK_KNIGHT_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv("DARK_KNIGHT_LANGUAGE", raising=False)
    project = ProjectRepository(tmp_path).create("Demo")

    async def run() -> None:
        shell = WorkbenchApp(project, data_dir=tmp_path)
        async with shell.run_test(size=(140, 40)) as pilot:
            await pilot.pause()
            await scenario(shell, pilot)

    asyncio.run(run())


def test_the_language_is_picked_from_a_list_and_the_project_stays(
    tmp_path, monkeypatch
) -> None:
    async def scenario(shell, pilot) -> None:
        await pilot.press("f4")
        await pilot.pause()
        assert isinstance(shell.screen, ChoiceDialog)
        options = shell.screen.query_one(OptionList)
        options.highlighted = 1
        await pilot.press("enter")
        await pilot.pause()

        sidebar = shell.query_one("#sidebar", OptionList)
        labels = [str(sidebar.get_option_at_index(i).prompt) for i in range(5)]
        assert any("PROJETOS" in label for label in labels)
        assert "ÁREA DE TRABALHO" in " ".join(labels)
        assert str(shell.query_one("#page-title", Static).render()) == "VISÃO GERAL"
        assert shell.project is not None and shell.project.id in str(
            shell.query_one("#header-project", Static).render()
        )
        assert "Atalho" in " ".join(e.help for e in shell.palette_entries())

    _run(tmp_path, monkeypatch, scenario)
    assert i18n.stored_language(tmp_path / "config") == "pt-BR"
