"""Countywide contests by city, for the site: site/data/city_totals.json.

Input
  data/rehearsal/<election id>_final_svc_precinct_public/   output of tools.svc_pipeline run on the county's SVC precinct PDF
  data/tidy/<election>/                                      the county API tables (contest titles, choice names, county totals)

Three joins, none of them guessed:
  1. SVC contest -> API contest: the API's title must appear in the contest's whole header text as a whole-word phrase (the
     longest such title wins, a tie is refused). Retention contests ("... - JOSHUA GROBAN" in the API, a long question in the
     PDF) match when both the part before " - " and the name appear. Layouts differ between elections, so we do not try to
     isolate "the title line". A header matching no API contest, or two equally well, is reported and left out.
  2. SVC vote column -> API choice: by the county total, not by column order. The PDF's printed GRAND TOTAL columns must equal
     the API's county votes as a set, exactly or, because the file is cut from one tally and our saved tally may be a moment
     later, within TOLERANCE of each value. Every value must have exactly one counterpart, and values close enough to be mixed up
     (neighbours within twice the allowance) refuse the contest. Equal zero totals are harmless.
  3. Cities: the pipeline's geometry-based city. Unincorporated places are summed into one "Unincorporated areas" entry,
     and ballots the pipeline could not place in any city are only counted.
The SVC is a file frozen at one moment of the count (a preliminary one in the first weeks, the certified one at the end), while the
API is live. So the SVC is matched to the saved API tally it equals: every saved tally (data/tidy results.csv) is tried and the one
that matches the most contests wins, ties going to the latest. The output says which tally that is. A contest that matches no saved
tally is left out and reported, never shown with mismatched numbers.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from sitegen.city_contests import city_key, read_csv
from tools.svc_parse import normalize_title

UNINC_PREFIX, UNASSIGNED_PREFIX = "UNINCORPORATED: ", "UNASSIGNED: "
TOLERANCE = 0.005  # a printed total may differ from our saved tally's by this share (the real 2026 file differs from our saved tally by about 0.05%)
SMALL = 3          # ...or by this many votes, for tiny totals


def match_columns(printed, api_votes, tolerance=TOLERANCE):
    """([choice index for each SVC column] or None, status, largest relative difference).
    status: ok | ok_approximate | totals_differ | ambiguous. Exact first; approximate pairs the sorted values and refuses
    any contest where two values are close enough to be swapped."""
    if len(printed) != len(api_votes):
        return None, "totals_differ", None
    if sorted(printed) == sorted(api_votes):
        nonzero = [v for v in printed if v]
        if len(nonzero) != len(set(nonzero)):
            return None, "ambiguous", 0.0
        used, mapping = set(), []
        for v in printed:
            j = next(i for i, a in enumerate(api_votes) if a == v and i not in used)
            used.add(j)
            mapping.append(j)
        return mapping, "ok", 0.0
    allow = lambda v: max(tolerance * v, SMALL)
    p_order = sorted(range(len(printed)), key=lambda i: printed[i])
    a_order = sorted(range(len(api_votes)), key=lambda j: api_votes[j])
    mapping, worst = [None] * len(printed), 0.0
    for i, j in zip(p_order, a_order):
        p, a = printed[i], api_votes[j]
        if abs(p - a) > max(allow(p), allow(a)):
            return None, "totals_differ", None
        worst = max(worst, abs(p - a) / max(p, a, 1))
        mapping[i] = j
    sorted_api = [api_votes[j] for j in a_order]
    for lo, hi in zip(sorted_api, sorted_api[1:]):
        if hi - lo <= 2 * (allow(lo) + allow(hi)):
            return None, "ambiguous", worst
    return mapping, "ok_approximate", worst


def header_score(api_title, header):
    """How well an API contest title is found in an SVC header: 0 = not found, else the matched length."""
    h = " ".join(header.upper().split())
    bounded = lambda phrase: bool(re.search(rf"(?<![A-Z0-9]){re.escape(phrase)}(?![A-Z0-9])", h))
    t = " ".join(api_title.upper().split())
    if bounded(t):
        return len(t)
    if " - " in t:  # retention contests: "FOR <office> - <NAME>" against a long question
        head, tail = t.split(" - ", 1)
        if bounded(head) and bounded(tail):
            return len(head) + len(tail)
    return 0


def match_contest(api, header):
    """(api contest or None, reason). The best-scoring API contest; a tie at the top is refused."""
    scored = sorted(((header_score(c["title"], header), c) for c in api.values()), key=lambda x: -x[0])
    if not scored or scored[0][0] == 0:
        return None, "no API contest title found in the header"
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None, "two API contests match equally well"
    return scored[0][1], "ok"


def api_structure(tidy):
    """(non-city contests, choices by contest id) from the API tables. No vote counts: those depend on the tally."""
    tidy = Path(tidy)
    choices = defaultdict(list)
    for ch in read_csv(tidy / "choices.csv"):
        choices[ch["contest_id"]].append(ch)
    return [c for c in read_csv(tidy / "contests.csv") if c["group"] != "Cities"], choices


def api_contests(structure, votes):
    """({normalised title: contest}, duplicate titles) with choices in API order and the county totals of one tally.
    votes = {choice_id: votes}."""
    contests, choices = structure
    out, dupes = {}, set()
    for c in contests:
        key = normalize_title(c["title"])
        if key in out:
            dupes.add(key)
        out[key] = {"id": int(c["contest_id"]), "title": c["title"], "group": c["group"], "kind": c["type"].lower(),
                    "choices": [{"name": ch["name"], "party": ch["party"], "votes": votes.get(ch["choice_id"], -1)} for ch in choices[c["contest_id"]]]}
    for key in dupes:
        out.pop(key, None)
    return out, sorted(dupes)


def saved_tallies(tidy):
    """{snapshot id: (county time, {choice_id: votes})} for every tally we saved."""
    out = {}
    for r in read_csv(Path(tidy) / "results.csv"):
        out.setdefault(r["snapshot"], (r["county_time"], {}))[1][r["choice_id"]] = int(r["votes"])
    return out


def pick_tally(structure, tallies, checks):
    """(contests matched, snapshot id, mean relative difference) of the saved tally closest to the SVC: most contests matched,
    then smallest differences, then the latest."""
    best = None
    for snap in sorted(tallies):
        api, _ = api_contests(structure, tallies[snap][1])
        n, gaps = 0, []
        for chk in checks:
            m, _ = match_contest(api, chk.get("header") or chk["title"])
            if m:
                mapping, status, gap = match_columns(json.loads(chk["printed_votes"]), [c["votes"] for c in m["choices"]])
                if mapping is not None:
                    n += 1
                    gaps.append(gap)
        mean = sum(gaps) / len(gaps) if gaps else 0.0
        if best is None or (n, -mean) >= (best[0], -best[2]):
            best = (n, snap, mean)
    return best


def build(svc_dir, tidy_dir, columns=None):
    """columns: optional list; each included contest appends (svc seq, contest id, column->choice mapping, number of choices)."""
    svc, tidy = Path(svc_dir), Path(tidy_dir)
    checks = read_csv(svc / "countywide_checks.csv")
    by_seq = defaultdict(list)
    for r in read_csv(svc / "countywide_by_city.csv"):
        by_seq[r["seq"]].append(r)
    structure, tallies = api_structure(tidy), saved_tallies(tidy)
    matched, snap, _ = pick_tally(structure, tallies, checks)
    county_time, votes = tallies[snap]
    api, dupes = api_contests(structure, votes)
    latest_snap = max(tallies)

    gaps, statuses = [], set()
    contests, report = [], {"unmatched_svc_titles": [], "refused": [], "api_title_duplicates": dupes, "included": 0,
                            "tally": {"snapshot": snap, "county_time": county_time, "is_latest": snap == latest_snap,
                                      "latest_county_time": tallies[latest_snap][0], "svc_contests_matching_it": matched, "svc_countywide_contests": len(checks)}}
    for chk in checks:
        title = chk["title"]
        header = chk.get("header") or title
        match, why = match_contest(api, header)
        if not match:
            report["unmatched_svc_titles"].append({"header": header[:200], "reason": why})
            continue
        printed = json.loads(chk["printed_votes"])
        mapping, status, gap = match_columns(printed, [c["votes"] for c in match["choices"]])
        if mapping is None:
            report["refused"].append({"title": match["title"], "reason": status, "printed": printed, "api": [c["votes"] for c in match["choices"]]})
            continue
        if columns is not None:
            columns.append((chk["seq"], match["id"], mapping, len(match["choices"])))
        gaps.append(gap)
        statuses.add(chk.get("status") or "")
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
                         "columns_in_api_order": mapping == list(range(n)), "difference_from_tally": round(gap, 5)})
    report["included"] = len(contests)
    report["tally"]["largest_difference"] = round(max(gaps), 5) if gaps else None
    report["tally"]["svc_status"] = sorted(x for x in statuses if x)
    return {"available": True, "tally": report["tally"], "contests": contests}, report


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
    columns = []
    out, report = build(svc, tidy, columns)
    from sitegen.precincts import write_precincts   # the map's precinct layer; needs the shapes the svc-rehearsal workflow saves
    print(write_precincts(svc, columns, dest))
    (dest / "city_totals.json").write_text(json.dumps(out, separators=(",", ":")))
    (dest / "city_totals_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"{report['included']} countywide contests with city totals; unmatched titles: {len(report['unmatched_svc_titles'])}; refused: {len(report['refused'])}")
