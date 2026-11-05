"""Build site/data/history.json: how every contest's numbers changed from tally to tally.

Each saved snapshot of the county counter data is one tally. History only starts when our collector
started saving, so tallies the county published before that are not in it.

Output: {"times": [{"snapshot", "county_time", "county_iso"}...],
         "ballots_counted": [EBLT per tally],
         "contests": {contest_id: {"ballots": [CBLT per tally],
                                   "choices": [{"name", "party", "votes": [votes per tally, null if missing]}]}}}
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sitegen.city_contests import read_csv


def county_iso(text):
    """'11/4/2026 3:11:55 AM' -> '2026-11-04T03:11:55' (county clock, no time zone), or None."""
    try:
        return datetime.strptime(text, "%m/%d/%Y %I:%M:%S %p").isoformat()
    except ValueError:
        return None


def drop_repeat_tallies(results):
    """Keep a snapshot only if its county time or any vote differs from the previous kept snapshot.
    The county API sometimes serves the same tally again (rows in a different order), which would show as a phantom tally."""
    by_snap = defaultdict(list)
    for r in results:
        by_snap[r["snapshot"]].append(r)
    kept, last = set(), None
    for snap in sorted(by_snap):
        rows = by_snap[snap]
        sig = (rows[0]["county_time"], tuple(sorted((r["choice_id"], r["votes"]) for r in rows)))
        if sig != last:
            kept.add(snap)
            last = sig
    return [r for r in results if r["snapshot"] in kept]


def build(tidy_dir):
    tidy = Path(tidy_dir)
    results = read_csv(tidy / "results.csv")
    results = drop_repeat_tallies(results)
    snapshots = sorted({r["snapshot"] for r in results})
    index = {s: i for i, s in enumerate(snapshots)}
    n = len(snapshots)
    time_of = {r["snapshot"]: r["county_time"] for r in results}

    votes = defaultdict(lambda: [None] * n)  # choice_id -> votes per tally
    for r in results:
        votes[r["choice_id"]][index[r["snapshot"]]] = int(r["votes"])

    ballots = defaultdict(lambda: [None] * n)  # contest_id -> CBLT per tally
    for r in read_csv(tidy / "contest_counters.csv"):
        if r["counter"] == "CBLT" and r["snapshot"] in index:  # snapshots dropped as repeats have no column
            ballots[r["contest_id"]][index[r["snapshot"]]] = int(r["value"])

    total = [None] * n
    for r in read_csv(tidy / "election_counters.csv"):
        if r["counter"] == "EBLT" and r["snapshot"] in index:
            total[index[r["snapshot"]]] = int(r["value"])

    contests = {}
    for ch in read_csv(tidy / "choices.csv"):
        c = contests.setdefault(ch["contest_id"], {"ballots": ballots[ch["contest_id"]], "choices": []})
        c["choices"].append({"name": ch["name"], "party": ch["party"], "votes": votes[ch["choice_id"]]})
    return {
        "times": [{"snapshot": s, "county_time": time_of[s], "county_iso": county_iso(time_of[s])} for s in snapshots],
        "ballots_counted": total,
        "contests": contests,
    }


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    out = build(f"data/tidy/{election}")
    dest = Path("site/data/history.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"{len(out['times'])} tallies, {len(out['contests'])} contests, {dest.stat().st_size // 1024} KB")
