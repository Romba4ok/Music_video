import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from pipeline import fetch_songs, song_identity, sources
from pipeline.common import Refused


TEXT = "трамвай увозит письма вдоль аллеи где сегодня пахнет мятой"
OTHER = "на крыше светит фонарь и ветер гонит по двору листья"


def test_lyrics_choose_second_catalog_when_both_label_the_track_identically(tmp_path, monkeypatch):
    song = {"artist": "Артист", "title": "Название", "sec": 0}
    monkeypatch.setattr(song_identity, "_references", lambda *args: (TEXT,))
    monkeypatch.setattr(song_identity, "_check_tags", lambda *args: None)
    monkeypatch.setattr(song_identity, "_samples", lambda path, lang: [path.read_text()])

    def download(candidate, dst, cfg):
        raw = dst / "raw.mp3"
        raw.write_text(OTHER if candidate.source == "first" else TEXT)
        return raw

    def catalog(site):
        return lambda *args: [sources.Candidate(site, "Название", "Артист", "https://test/" + site)]

    cfg = {"sources": {"order": ["first", "second"]}, "licenses_allowed": []}
    name, reason = fetch_songs.fetch_one(song, cfg, tmp_path, {s: catalog(s) for s in cfg["sources"]["order"]},
                                        download, lambda path, **kw: (path, []), download_only=True)
    assert "second" in reason and (tmp_path / name).read_text() == TEXT
    assert len(list(tmp_path.iterdir())) == 2  # one accepted file and its sidecar


def test_no_reference_never_accepts_metadata_alone(monkeypatch):
    monkeypatch.setattr(song_identity, "_check_tags", lambda *args: None)
    monkeypatch.setattr(song_identity, "_references", lambda *args: ())
    with pytest.raises(Refused, match="no reference"):
        song_identity.verify(Path("unused"), "Артист", "Название")


def test_queue_line_can_confirm_second_excerpt(monkeypatch):
    monkeypatch.setattr(song_identity, "_check_tags", lambda *args: None)
    monkeypatch.setattr(song_identity, "_references", lambda *args: ())
    monkeypatch.setattr(song_identity, "_samples", lambda *args: [OTHER, TEXT])
    assert song_identity.verify(Path("unused"), "А", "Т", "вдоль аллеи где сегодня") == "queue lyrics matched"


def test_reference_lookup_drops_same_title_from_other_artists(monkeypatch):
    rows = [dict(trackName="Название", artistName=a, plainLyrics=t)
            for a, t in [("Другой", OTHER), ("Артист", TEXT)]]
    monkeypatch.setattr(song_identity, "get_json", lambda *args, **kwargs: rows)
    assert song_identity._references.__wrapped__("Артист", "Название") == (TEXT,)


def test_crediting_requested_artist_as_guest_does_not_confirm_the_lead(monkeypatch):
    tags = {"artist": "Другой feat. Артист", "title": "Название"}
    result = CompletedProcess([], 0, stdout=json.dumps({"format": {"tags": tags}}))
    monkeypatch.setattr(song_identity.subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(Refused, match="embedded artist"):
        song_identity.verify(Path("unused"), "Артист", "Название")
