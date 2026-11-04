"""Turn raw county API snapshots into tidy CSV tables.

Reads  data/raw/<election>/rrcc_api_election_data  (contest structure, no live votes)
       data/raw/<election>/rrcc_api_counter_data   (live numbers, one file per snapshot)
Writes data/tidy/<election>/{contests,choices,results,contest_counters,election_counters}.csv

The raw files are never changed. Counter types we do not understand yet are kept as they are,
not dropped, so nothing is lost while we work out what they mean.
"""
import csv
import json
import sys
from pathlib import Path

# Election-wide counters: ReferenceID is the election id. Meaning of EBLT/MBLT comes from the
# county's own JS (total ballots / vote-by-mail). The others are kept but not yet interpreted.
ELECTION_TYPES = {"EBLT", "MBLT", "DBLT", "ECRD", "MCRD", "DCRD", "PBLT"}


def load(path):
    return json.loads(Path(path).read_text())


def latest(source_dir):
    snaps = sorted(p for p in Path(source_dir).iterdir() if (p / "body").exists())
    return snaps[-1] / "body"


def parse_structure(payload):
    """Returns (election_info, contests, choices) from GetElectionData."""
    d = payload["Data"]
    info = {
        "election_id": d["ID"], "title": d["Title"], "date": d["Date"][:10],
        "registered": d["RegistrationCount"],
    }
    contests, choices = [], []
    for group in d["ContestGroups"]:
        for c in group["Contests"]:
            contests.append({
                "contest_id": c["ID"], "group": group["Name"], "group_order": group["Order"],
                "title": c["Title"], "type": c["Type"], "vote_for": c["VoteFor"],
                "pass_rate": c.get("MeasurePassRate") or "",
                "measure_text": (c.get("MeasureText") or "").strip(),
            })
            for ch in c["Candidates"]:
                choices.append({
                    "contest_id": c["ID"], "choice_id": ch["ID"],
                    "name": ch["Name"], "party": ch["Party"],
                })
    return info, contests, choices


def parse_counters(payload, snapshot):
    """Split GetCounterData into candidate votes, per-contest counters, election-wide counters.

    snapshot is the folder name of the raw snapshot; county_time is the county's own timestamp.
    """
    county_time = payload["TimeStamp"]
    results, contest_counters, election_counters = [], [], []
    for r in payload["Data"]:
        t, ref, v = r["ReferenceType"], r["ReferenceID"], r["Value"]
        base = {"snapshot": snapshot, "county_time": county_time}
        if t == "CAND":
            results.append({**base, "choice_id": ref, "votes": int(v)})
        elif t in ELECTION_TYPES:
            election_counters.append({**base, "counter": t, "value": int(v)})
        else:  # CBLT, CUV, COV, CPV, CFV, NSEL-*, WRTN-*: ReferenceID is the contest id
            contest_counters.append({**base, "contest_id": ref, "counter": t, "value": int(v)})
    return results, contest_counters, election_counters


def check(contests, choices, results, contest_counters):
    """Return a list of problems. Empty list means the joins are clean."""
    problems = []
    contest_ids = {c["contest_id"] for c in contests}
    choice_ids = {c["choice_id"] for c in choices}
    for r in results:
        if r["choice_id"] not in choice_ids:
            problems.append(f"result for unknown choice {r['choice_id']}")
    for r in contest_counters:
        if r["contest_id"] not in contest_ids:
            problems.append(f"counter {r['counter']} for unknown contest {r['contest_id']}")
    return problems


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def run(raw_election_dir, tidy_election_dir):
    raw, tidy = Path(raw_election_dir), Path(tidy_election_dir)
    info, contests, choices = parse_structure(load(latest(raw / "rrcc_api_election_data")))
    results, ccount, ecount = [], [], []
    for snap in sorted((raw / "rrcc_api_counter_data").iterdir()):
        if not (snap / "body").exists():
            continue
        r, c, e = parse_counters(load(snap / "body"), snap.name)
        results += r
        ccount += c
        ecount += e
    problems = check(contests, choices, results, ccount)
    write_csv(tidy / "contests.csv", contests, ["contest_id", "group", "group_order", "title", "type", "vote_for", "pass_rate", "measure_text"])
    write_csv(tidy / "choices.csv", choices, ["contest_id", "choice_id", "name", "party"])
    write_csv(tidy / "results.csv", results, ["snapshot", "county_time", "choice_id", "votes"])
    write_csv(tidy / "contest_counters.csv", ccount, ["snapshot", "county_time", "contest_id", "counter", "value"])
    write_csv(tidy / "election_counters.csv", ecount, ["snapshot", "county_time", "counter", "value"])
    (tidy / "election.json").write_text(json.dumps(info, indent=2) + "\n")
    return {"contests": len(contests), "choices": len(choices), "result_rows": len(results), "problems": problems}


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    out = run(f"data/raw/{election}", f"data/tidy/{election}")
    print({k: v for k, v in out.items() if k != "problems"}, "problems:", len(out["problems"]))
    for p in out["problems"][:10]:
        print(" ", p)
    sys.exit(1 if out["problems"] else 0)
