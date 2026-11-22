import json

from pipeline.audio_inventory import inventory


def test_inventory_counts_old_and_new_audio_and_separates_unreadable_metadata(tmp_path):
    names = ["owned.MP3", "new.mp3", "licensed.ogg", "broken.flac", "missing.m4a", "notes.txt"]
    for filename, data in [("new.mp3", '{"analysis_only": true}'), ("licensed.ogg", '{"license":"by"}'),
                           ("broken.flac", "{"), ("missing.m4a", None)]:
        side = filename + ".license.json"
        names.append(side)
        if data is not None:
            (tmp_path / side).write_text(data)
    listing = [{"Name": n, "IsDir": False} for n in names] + [{"Name": "folder.mp3", "IsDir": True}]
    report = inventory(listing, tmp_path)
    assert "Drive/audio: **5**" in report and "AUTO: **2**" in report
    assert "без .license.json — 1" in report and "анализа: 1" in report and "проверить: 2" in report


def test_inventory_predicts_generate_for_full_downloads_and_previews(tmp_path, monkeypatch):
    # The standalone fetch workflow does not inherit the generate workflow's env.
    monkeypatch.delenv("VYBEX_OWNER_DECLARES_RIGHTS", raising=False)
    listing = []
    for name, flags in [
        ("full1", {"download_only": True}),
        ("full2", {"download_only": True}),
        ("full3", {"download_only": True}),
        ("preview", {"license": "official-preview"}),
        ("analysis", {"download_only": False}),
        ("invalid", {"download_only": "false"}),
    ]:
        audio = name + ".mp3"
        side = audio + ".license.json"
        listing.extend([{"Name": audio}, {"Name": side}])
        (tmp_path / side).write_text(json.dumps({"analysis_only": True, **flags}), encoding="utf-8")

    report = inventory(listing, tmp_path)
    assert "Drive/audio: **6**" in report
    assert "AUTO: **3**" in report
    assert "полные треки с download_only — 3" in report
    assert "анализа: 2" in report and "проверить: 1" in report
