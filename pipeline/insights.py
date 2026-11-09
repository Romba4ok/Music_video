"""What works: joins accounts/<acc>/cards.jsonl (what each video was made of, written by the batch) with accounts/<acc>/views.csv
(`song,views` rows: copy the numbers from the TikTok profile, there is no official free read API) and prints views by feature.

python -m pipeline insights [--acc main]
Few videos mean noise: the tool says so instead of drawing conclusions from fewer than 5 matched videos."""
import csv
import statistics
from pathlib import Path

from .batch import recall_cards
from .common import ROOT

MIN_VIDEOS = 5


def load_views(path):
    f = Path(path)
    if not f.exists():
        return {}
    with open(f, encoding="utf-8", newline="") as fh:
        return {r["song"].strip().lower(): int(r["views"]) for r in csv.DictReader(fh) if r.get("song") and str(r.get("views", "")).strip().isdigit()}


def table(cards, views):
    """-> [(feature, group, n, median views)] over videos that have both a card record and a view count."""
    rows = [dict(c, views=views[c["song"].lower()]) for c in cards if c["song"].lower() in views]
    feats = {"theme": lambda r: r.get("theme", "light"), "draw share": lambda r: "2/3+" if r.get("draw_share", 0) >= .66 else "less",
             "app details (big/chips)": lambda r: "3+" if r.get("details", 0) >= 3 else "fewer", "cards": lambda r: "9+" if r.get("n_cards", 0) >= 9 else "fewer",
             "renderer": lambda r: r.get("renderer", "hyperframes"),  # old rows have no field: made before the Remotion move (frame-by-frame cards)
             "objects move (tw)": lambda r: "half+" if r.get("anim_share", 0) >= .5 else "less",
             "hook is a question": lambda r: "yes" if r.get("hook_question", str(r.get("hook", "")).endswith("?")) else "no"}
    out = []
    for name, key in feats.items():
        groups = {}
        for r in rows:
            groups.setdefault(key(r), []).append(r["views"])
        out += [(name, g, len(v), int(statistics.median(v))) for g, v in sorted(groups.items())]
    return rows, out


def main(argv):
    acc = ROOT / "accounts" / (argv[argv.index("--acc") + 1] if "--acc" in argv else "main")
    rows, out = table(recall_cards(acc, 1000), load_views(acc / "views.csv"))
    print(f"{len(rows)} videos with both a card record and views (need >= {MIN_VIDEOS} for any conclusion)")
    for r in sorted(rows, key=lambda r: -r["views"]):
        print(f'{r["views"]:>7}  {r["song"]}  [{r.get("theme", "light")}, {r["n_cards"]} cards, draw {r.get("draw_share")}]  {r.get("hook", "")}')
    if len(rows) >= MIN_VIDEOS:
        print()
        for name, g, n, med in out:
            print(f"{name:<26}{g:<8} n={n:<3} median views {med}")
    return 0
