"""Summarize the AUTO input metadata after fetch-songs uploads files to Drive."""
import argparse
import json
from pathlib import Path

from .batch import AUDIO_EXT


def inventory(listing, metadata_dir):
    # A missing sidecar in Drive is a normal owner-supplied input to generate.
    # A listed sidecar that could not be read locally is a different case.
    names = [entry["Name"] for entry in listing if not entry.get("IsDir")]
    listed = set(names)
    local = {p.name: p for p in metadata_dir.glob("*.license.json")}
    total = ready = analysis = unknown = owner_files = declared_downloads = 0
    for name in names:
        if Path(name).suffix.lower() not in AUDIO_EXT:
            continue
        total += 1
        side = name + ".license.json"
        if side not in listed:
            ready += 1
            owner_files += 1
            continue
        try:
            meta = json.loads(local[side].read_text(encoding="utf-8"))
        except (KeyError, OSError, ValueError):
            unknown += 1
            continue
        if not isinstance(meta, dict) or not isinstance(meta.get("analysis_only", False), bool):
            unknown += 1
        elif meta.get("analysis_only") and not isinstance(meta.get("download_only", False), bool):
            unknown += 1
        elif meta.get("analysis_only") and meta.get("download_only"):
            # This report describes Drive inputs to generate.yml, which sets
            # VYBEX_OWNER_DECLARES_RIGHTS=1 even when fetch-songs runs on its own.
            declared_downloads += 1
            ready += 1
        elif meta.get("analysis_only"):
            analysis += 1
        else:
            ready += 1
    return (f"Файлов в Drive/audio: **{total}**. Допущено по метаданным для AUTO: **{ready}** "
            f"(по декларации владельца в generate: без .license.json — {owner_files}, "
            f"полные треки с download_only — {declared_downloads}). "
            f"Только для анализа: {analysis}. Метаданные не удалось проверить: {unknown}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("listing", type=Path)
    parser.add_argument("metadata_dir", type=Path)
    args = parser.parse_args()
    print(inventory(json.loads(args.listing.read_text(encoding="utf-8")), args.metadata_dir))
