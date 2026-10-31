import pytest

from qa_workbench import i18n


@pytest.fixture(autouse=True)
def english():
    """The interface language is global state: every test starts in English."""
    i18n.set_language(i18n.ENGLISH)
    yield
    i18n.set_language(i18n.ENGLISH)
