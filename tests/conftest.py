import pytest


@pytest.fixture(autouse=True)
def no_claude(monkeypatch):
    """Tests never call the real Claude CLI."""
    monkeypatch.setenv("VYBEX_NO_AUTHOR", "1")


@pytest.fixture(autouse=True)
def no_official_network(monkeypatch, request):
    """The official-source stage reaches the real MusicBrainz/artist sites: tests get an empty stage unless they test it (marker `official`)."""
    if "test_official" not in request.node.fspath.basename:
        from pipeline import official
        monkeypatch.setattr(official, "try_song", lambda w, cfg, out, known=(), **k: {"file": None, "detail": "", "links": [], "reason": ""})
