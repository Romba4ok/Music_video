import pytest


@pytest.fixture(autouse=True)
def no_claude(monkeypatch):
    """Tests never call the real Claude CLI."""
    monkeypatch.setenv("VYBEX_NO_AUTHOR", "1")
