"""Build site/data/county_contests.json: every non-city contest (statewide, county, district, school...).

These come from the county results API as county totals. For a contest that spans several counties
(some congressional and state senate districts) the number is the Los Angeles County part only.
Election-wide totals (ballots counted, vote-by-mail) use the counters the county's own results page uses:
EBLT = total ballots, MBLT = vote-by-mail ballots.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from sitegen.city_contests import contest_record, latest_numbers, read_csv


def election_totals(tidy, snapshot, registered):
    counters = {r["counter"]: int(r["value"]) for r in read_csv(tidy / "election_counters.csv")
                if r["snapshot"] == snapshot}
    ballots = counters.get("EBLT")
    return {
        "registered": registered, "ballots_counted": ballots, "vote_by_mail_ballots": counters.get("MBLT"),
        "share_of_registered": round(ballots / registered, 4) if ballots is not None and registered else None,
    }


def build(tidy_dir):
    tidy = Path(tidy_dir)
    info = json.loads((tidy / "election.json").read_text())
    contests = [c for c in read_csv(tidy / "contests.csv") if c["group"] != "Cities"]
    choices = defaultdict(list)
    for ch in read_csv(tidy / "choices.csv"):
        choices[ch["contest_id"]].append(ch)
    latest, county_time, votes, ballots = latest_numbers(tidy)

    groups = {}
    for c in contests:
        g = groups.setdefault(c["group"], {"name": c["group"], "order": int(c["group_order"]), "contests": []})
        rec = contest_record(c, c["title"].title() if c["title"].isupper() else c["title"], choices[c["contest_id"]], votes, ballots)
        g["contests"].append(rec)
    ordered = sorted(groups.values(), key=lambda g: (g["order"], g["name"]))
    for g in ordered:
        g["contests"].sort(key=lambda x: x["label"])
    return {
        "election": {"title": info["title"], "date": info["date"]},
        "county_time": county_time, "snapshot": latest,
        "totals": election_totals(tidy, latest, info["registered"]),
        "groups": ordered,
    }


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    out = build(f"data/tidy/{election}")
    dest = Path("site/data/county_contests.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    n = sum(len(g["contests"]) for g in out["groups"])
    print(f"{len(out['groups'])} groups, {n} contests, totals: {out['totals']}")
