"""Countywide contests by city, for the site: site/data/city_totals.json.

Input
  data/rehearsal/<election id>_final_svc_precinct_public/   output of tools.svc_pipeline run on the county's SVC precinct PDF
  data/tidy/<election>/                                      the county API tables (contest titles, choice names, county totals)

Three joins, none of them guessed:
  1. SVC contest -> API contest: by title, case and spacing normalised ("Voter Nominated :" removed). No fuzzy matching.
     A title with no match, or matched by two API contests, is reported and left out.
  2. SVC vote column -> API choice: by the county total. The PDF's printed GRAND TOTAL columns must equal the API's county
     votes as a set; each column is given to the choice with the same total. Column order is NOT assumed. If two choices
     have the same non-zero total the contest is refused (it cannot be told apart); equal zero totals are harmless.
  3. Cities: the pipeline's geometry-based city. Unincorporated places are summed into one "Unincorporated areas" entry,
     and ballots the pipeline could not place in any city are only counted.
The SVC is published after certification, the API is live. A contest whose totals do not match yet (the count moved on) is
left out and reported, never shown with mismatched numbers.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from sitegen.city_contests import city_key, latest_numbers, read_csv
from tools.svc_parse import normalize_title

UNINC_PREFIX, UNASSIGNED_PREFIX = "UNINCORPORATED: ", "UNASSIGNED: "


def match_columns(printed, api_votes):
    """([choice index for each SVC column] or None, status). Matches by total; refuses ambiguous non-zero ties."""
    if sorted(printed) != sorted(api_votes):
        return None, "totals_differ"
    nonzero = [v for v in printed if v]
    if len(nonzero) != len(set(nonzero)):
        return None, "ambiguous_equal_totals"
    used, mapping = set(), []
    for v in printed:
        j = next(i for i, a in enumerate(api_votes) if a == v and i not in used)
        used.add(j)
        mapping.append(j)
    return mapping, "ok"


def api_contests(tidy):
    """{normalised title: contest} for non-city contests, with choices in API order and the latest county totals."""
    tidy = Path(tidy)
    snapshot, county_time, votes, ballots = latest_numbers(tidy)
    choices = defaultdict(list)
    for ch in read_csv(tidy / "choices.csv"):
        choices[ch["contest_id"]].append({"name": ch["name"], "party": ch["party"], "votes": votes[ch["choice_id"]]})
    out, dupes = {}, set()
    for c in read_csv(tidy / "contests.csv"):
        if c["group"] == "Cities":
            continue
        key = normalize_title(c["title"])
        if key in out:
            dupes.add(key)
        out[key] = {"id": int(c["contest_id"]), "title": c["title"], "group": c["group"], "kind": c["type"].lower(),
                    "choices": choices[c["contest_id"]]}
    for key in dupes:
        out.pop(key, None)
    return out, sorted(dupes), county_time


def build(svc_dir, tidy_dir):
    svc, tidy = Path(svc_dir), Path(tidy_dir)
    checks = read_csv(svc / "countywide_checks.csv")
    by_seq = defaultdict(list)
    for r in read_csv(svc / "countywide_by_city.csv"):
        by_seq[r["seq"]].append(r)
    api, dupes, county_time = api_contests(tidy)

    contests, report = [], {"unmatched_svc_titles": [], "refused": [], "api_title_duplicates": dupes, "included": 0}
    for chk in checks:
        title = chk["title"]
        match = api.get(normalize_title(title))
        if not match:
            report["unmatched_svc_titles"].append(title)
            continue
        printed = json.loads(chk["printed_votes"])
        mapping, status = match_columns(printed, [c["votes"] for c in match["choices"]])
        if status != "ok":
            report["refused"].append({"title": title, "reason": status, "printed": printed, "api": [c["votes"] for c in match["choices"]]})
            continue
        n = len(match["choices"])
        cities, unincorp, unassigned = {}, None, 0
        for r in by_seq[chk["seq"]]:
            votes = [0] * n
            for col, j in enumerate(mapping):
                votes[j] = int(r[f"choice_{col + 1}"])
            entry = {"ballots": int(r["ballots"]), "registration": int(r["registration"]),
                     "fallback_ballots": int(r["ballots_fallback"]), "votes": votes, "precincts": int(r["precincts"])}
            name = r["city"]
            if name.startswith(UNASSIGNED_PREFIX):
                unassigned += entry["ballots"]
            elif name.startswith(UNINC_PREFIX):
                if unincorp is None:
                    unincorp = {"name": "Unincorporated areas", "ballots": 0, "registration": 0, "fallback_ballots": 0, "precincts": 0, "votes": [0] * n}
                for k in ("ballots", "registration", "fallback_ballots", "precincts"):
                    unincorp[k] += entry[k]
                unincorp["votes"] = [a + b for a, b in zip(unincorp["votes"], votes)]
            else:
                cities[city_key(name)] = {"name": name, **entry}
        if unincorp:
            cities["unincorporated"] = unincorp
        # every vote is somewhere: cities + unincorporated + unassigned places must add up to the county total
        total = [sum(c["votes"][j] for c in cities.values()) for j in range(n)]
        shortfall = [a["votes"] - t for a, t in zip(match["choices"], total)]  # votes that sit in unassigned places
        contests.append({"id": match["id"], "label": match["title"], "group": match["group"], "kind": match["kind"],
                         "choices": [{"name": c["name"], "party": c["party"], "county_votes": c["votes"]} for c in match["choices"]],
                         "cities": cities, "unassigned_ballots": unassigned, "votes_not_in_a_city_or_unincorporated": shortfall,
                         "columns_in_api_order": mapping == list(range(n))})
    report["included"] = len(contests)
    return {"available": True, "county_time": county_time, "contests": contests}, report


def find_svc_dir(tidy_dir, root="data/rehearsal"):
    """The pipeline output for this election's SVC precinct file: <election id>_*precinct*, preferring a name containing "final"."""
    info = json.loads((Path(tidy_dir) / "election.json").read_text())
    found = [d for d in Path(root).glob(f"{info['election_id']}_*precinct*") if (d / "countywide_checks.csv").exists()] if Path(root).exists() else []
    if not found:
        return None
    final = [d for d in found if re.search(r"(^|[^a-z])final", d.name.lower())]  # whole word: "semifinal" is not final
    return sorted(final or found)[-1]


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    tidy = f"data/tidy/{election}"
    svc = find_svc_dir(tidy)
    dest = Path("site/data")
    dest.mkdir(parents=True, exist_ok=True)
    if svc is None:
        (dest / "city_totals.json").write_text(json.dumps({"available": False, "reason": "The county has not published the precinct-level Statement of Votes Cast for this election yet."}))
        print("no SVC output for this election yet: city totals not available")
        sys.exit(0)
    out, report = build(svc, tidy)
    (dest / "city_totals.json").write_text(json.dumps(out, separators=(",", ":")))
    (dest / "city_totals_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"{report['included']} countywide contests with city totals; unmatched titles: {len(report['unmatched_svc_titles'])}; refused: {len(report['refused'])}")
