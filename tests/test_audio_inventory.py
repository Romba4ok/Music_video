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
    assert "включая 1 без" in report and "анализа: 1" in report and "проверить: 2" in report
