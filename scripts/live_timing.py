"""
Rewrites the LIVE TIMING bit of the profile README after every race.

Grabs PitWall's saved prediction for the latest race (data/snapshots in the PitWall
repo) and the real results (race_results_2026.csv, which PitWall's own Monday job
updates), then checks how close the prediction was. Only uses the standard library
so the GitHub Action doesn't need to install anything.
"""

import csv
import io
import json
import os
import re
import urllib.request

REPO = "pyyroo-a/Formula-1-Fantasy-Predictor"
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
YEAR = 2026
README = os.path.join(os.path.dirname(__file__), "..", "README.md")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pyyroo-a-profile"})
    # the action passes its token so we don't hit GitHub's rate limit
    token = os.getenv("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def load_results():
    rows = csv.DictReader(io.StringIO(fetch(f"{RAW}/data/processed/race_results_{YEAR}.csv")))
    races = {}
    for row in rows:
        races.setdefault(int(row["RoundNumber"]), []).append(row)
    return races


def latest_scored_snapshot(races):
    # newest snapshot whose race already has results, e.g. skip this weekend's if it hasn't happened yet
    files = json.loads(fetch(f"https://api.github.com/repos/{REPO}/contents/data/snapshots"))
    names = sorted(f["name"] for f in files if f["name"].startswith(f"{YEAR}_R") and f["name"].endswith(".json"))
    for name in reversed(names):
        snap = json.loads(fetch(f"{RAW}/data/snapshots/{name}"))
        if int(snap["round"]) in races and snap.get("finishes"):
            return snap
    return None


def build_section(snap, results):
    finished = [r for r in results if r["Status"] not in ("DNF", "DSQ", "DNS")]
    actual_pos = {r["Abbreviation"]: float(r["Position"]) for r in finished}
    by_pos = sorted(results, key=lambda r: float(r["Position"]))
    winner = by_pos[0]
    actual_podium = {r["Abbreviation"] for r in by_pos[:3]}

    predicted = sorted(snap["finishes"], key=lambda f: f["model_pos"])
    predicted_winner = predicted[0]["abbreviation"]
    podium_hits = len({f["abbreviation"] for f in predicted[:3]} & actual_podium)

    # average places off, only for drivers who actually finished (a DNF isn't a prediction miss)
    errors = [abs(f["model_pos"] - actual_pos[f["abbreviation"]]) for f in predicted if f["abbreviation"] in actual_pos]
    avg_off = sum(errors) / len(errors)

    race = snap["race_name"].replace("Grand Prix", "GP")
    called = "✅ winner" if predicted_winner == winner["Abbreviation"] else f"❌ winner (had {predicted_winner})"

    return (
        f"**{race} (R{int(snap['round'])})**\n\n"
        f"🏆 Winner: **{winner['FullName']}**<br/>\n"
        f"🔮 PitWall called it: {called} · **{podium_hits}/3** podium<br/>\n"
        f"📏 Predicted order off by **{avg_off:.1f}** places on average\n\n"
        f"<sub>auto-updated every Monday by a GitHub Action, straight from "
        f"[PitWall's saved predictions](https://github.com/{REPO}/tree/main/data/snapshots)</sub>"
    )


def main():
    races = load_results()
    snap = latest_scored_snapshot(races)
    if snap is None:
        print("no race with both a prediction and results yet, leaving README alone")
        return

    section = build_section(snap, races[int(snap["round"])])
    with open(README, encoding="utf-8") as f:
        readme = f.read()
    new = re.sub(
        r"(<!-- LIVE-TIMING:START -->).*?(<!-- LIVE-TIMING:END -->)",
        lambda m: m.group(1) + "\n" + section + "\n" + m.group(2),
        readme,
        flags=re.S,
    )
    with open(README, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"updated live timing for {snap['race_name']}")


if __name__ == "__main__":
    main()
