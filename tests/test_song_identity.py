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


def test_lookup_finds_guest_credited_in_artist_instead_of_title(monkeypatch):
    def search(url, params, **kwargs):
        assert params == {"artist_name": "Xcho", "track_name": "Ветер"}
        return [dict(trackName="Ветер", artistName="Xcho feat. " + guest, plainLyrics=lyrics)
                for guest, lyrics in [("DanRi", TEXT), ("Другой", OTHER)]]

    monkeypatch.setattr(song_identity, "get_json", search)
    assert song_identity._references.__wrapped__("Xcho", "Ветер (feat. DanRi)") == (TEXT,)


def test_crediting_requested_artist_as_guest_does_not_confirm_the_lead(monkeypatch):
    tags = {"artist": "Другой feat. Артист", "title": "Название"}
    result = CompletedProcess([], 0, stdout=json.dumps({"format": {"tags": tags}}))
    monkeypatch.setattr(song_identity.subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(Refused, match="embedded artist"):
        song_identity.verify(Path("unused"), "Артист", "Название")


@pytest.mark.parametrize("asked_artist,asked_title,artist,title,expected", [
    ("Xcho", "Ветер", "Xcho feat. DanRi", "Ветер", True),
    ("Xcho", "Ветер", "DanRi feat. Xcho", "Ветер", False),
    ("Xcho", "Ветер (feat. DanRi)", "Xcho/DanRi", "Ветер", True),
    ("Xcho & DanRi", "Ветер", "Xcho", "Ветер (ft. Другой)", False),
    ("Xcho", "Ветер", "Xcho", "Ветер (feat. DanRi Remix)", False),
])
def test_match_featured_artists(asked_artist, asked_title, artist, title, expected):
    track = sources.Candidate("tags", title, artist)
    assert sources.matches(asked_artist, asked_title, track, collaborations=True) is expected


def test_auto_detect_language_for_each_excerpt(monkeypatch):
    from types import SimpleNamespace
    import numpy as np

    calls = []

    def transcribe(sample, **kwargs):
        calls.append((kwargs["language"], sample[0]))
        return [SimpleNamespace(text=TEXT if len(calls) == 2 else OTHER, avg_logprob=-0.4, no_speech_prob=0)], None

    monkeypatch.setattr(song_identity, "_pcm16k", lambda p: np.arange(90 * 16000))
    monkeypatch.setattr(song_identity, "_model", lambda: SimpleNamespace(transcribe=transcribe))
    monkeypatch.setattr(song_identity, "_references", lambda *args: (TEXT,))
    monkeypatch.setattr(song_identity, "_check_tags", lambda *args: None)
    assert song_identity.verify("file", "Артист", "Название") == "LRCLIB lyrics matched"
    assert [lang for lang, pos in calls] == [None, None] and calls[1][1] > calls[0][1]
