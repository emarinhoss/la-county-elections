"""Precinct layer for the map: site/data/precincts.json (votes) and site/data/precincts.geojson (shapes).

Input
  data/rehearsal/<name>/precinct_votes.csv.gz   every precinct's votes in each countywide contest, columns as printed in the SVC
  data/rehearsal/<name>/precinct_city.csv       the city (found from the shape) of each precinct
  data/rehearsal/<name>/precinct_shapes.geojson polygons of the precincts in that SVC file (saved by the svc-rehearsal workflow)
The vote columns are put into the API's choice order with the same column mapping city_totals used for that contest, so the
precinct numbers and the city numbers come from one matching. A contest city_totals left out is left out here too.

precincts.json: {"p": {precinct id: {"city": key, "v": {contest id: [registration, ballots, votes in API choice order]}}}}
"""
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

from sitegen.city_contests import city_key, read_csv
from sitegen.city_totals import api_contests, match_columns, match_contest, saved_tallies


def build(svc_dir, columns, vbm=False):
    """{"p": {precinct id: {"city": key, "v": {contest id: row}}}}. row = [registration, ballots, votes in API choice order] for all
    ballots, or [vbm ballots, vbm votes in API choice order] when vbm=True (empty if the file predates the vote-by-mail columns)."""
    svc = Path(svc_dir)
    where = {}
    for r in csv.DictReader(open(svc / "precinct_city.csv", newline="")):
        c = r["city"]
        where[r["precinct"]] = "" if c.startswith("UNASSIGNED: ") else "unincorporated" if c.startswith("UNINCORPORATED: ") else city_key(c)
    by_seq = {c[0]: c[1:4] for c in columns}
    precincts = defaultdict(lambda: {"city": "", "v": {}})
    with gzip.open(svc / "precinct_votes.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["seq"] not in by_seq:
                continue
            if vbm and r.get("vbm_ballots", "") == "":
                continue
            cid, mapping, n = by_seq[r["seq"]]
            votes = [0] * n
            for col, j in enumerate(mapping):
                votes[j] = int(r[f"{'vbm_' if vbm else ''}choice_{col + 1}"])
            p = precincts[r["precinct"]]
            p["city"] = where.get(r["precinct"], "")
            p["v"][str(cid)] = [int(r["vbm_ballots"]), *votes] if vbm else [int(r["registration"]), int(r["ballots"]), *votes]
    return {"p": dict(precincts)}


# The shapes are the county's consolidated Election Precincts (the unit the SVC reports); tools/election_precincts.py checks that every
# SVC precinct id has a polygon and writes election_layer_match.json. Set to False to hide the layer without deleting anything.
PUBLISH = True


def city_columns(svc_dir, tidy_dir, snapshot, skip_seqs):
    """Match the SVC's non-countywide blocks (city contests) to the API's city contests, the same safe way city_totals does it:
    the API title must appear in the block's header text, and the vote columns are matched by county total at the saved tally the
    SVC equals. A block that matches no contest, or whose totals disagree, is left out and counted in the report.
    Returns ([(seq, contest id, mapping, n, names)], report)."""
    svc, tidy = Path(svc_dir), Path(tidy_dir)
    checks = svc / "all_blocks_check.csv"
    report = {"city_blocks_seen": 0, "matched": 0, "unmatched_header": 0, "refused_totals": 0, "refused_examples": []}
    if not checks.exists():
        return [], {**report, "note": "all_blocks_check.csv missing: rerun svc-rehearsal"}
    choices = defaultdict(list)
    for ch in read_csv(tidy / "choices.csv"):
        choices[ch["contest_id"]].append(ch)
    cities = [c for c in read_csv(tidy / "contests.csv") if c["group"] == "Cities"]
    votes = saved_tallies(tidy)[snapshot][1]
    api, _dupes = api_contests((cities, choices), votes)
    out, seen = [], set()
    for chk in read_csv(checks):
        if chk["seq"] in skip_seqs:
            continue
        report["city_blocks_seen"] += 1
        match, _why = match_contest(api, chk["header"] or chk["title"])
        if not match or match["id"] in seen:
            report["unmatched_header"] += 1
            continue
        mapping, status, _gap = match_columns(json.loads(chk["printed_votes"]), [c["votes"] for c in match["choices"]])
        if mapping is None or chk["votes_match_printed"] != "True":
            report["refused_totals"] += 1
            if len(report["refused_examples"]) < 10:
                report["refused_examples"].append({"title": match["title"], "reason": status if mapping is None else "precinct rows do not add to the printed total"})
            continue
        seen.add(match["id"])
        out.append((chk["seq"], match["id"], mapping, len(match["choices"]), [c["name"] for c in match["choices"]]))
        report["matched"] += 1
    return out, report


def write_precincts(svc_dir, columns, dest, publish=PUBLISH, report=None):
    dest = Path(dest)
    svc = Path(svc_dir)
    if not publish:
        for name in ("precincts.json", "precincts.geojson", "precincts_method.json"):
            (dest / name).unlink(missing_ok=True)
        return "precinct layer switched off (PUBLISH is False)"
    shapes_file = svc / "precinct_shapes.geojson"
    if not (svc / "precinct_votes.csv.gz").exists() or not shapes_file.exists():
        for name in ("precincts.json", "precincts.geojson", "precincts_method.json"):
            (dest / name).unlink(missing_ok=True)
        return "precinct layer not available yet (needs a svc-rehearsal run that saves precinct votes and shapes)"
    data = build(svc, columns)
    data["names"] = {str(c[1]): c[4] for c in columns if len(c) > 4}      # choice names in the order of each contest's vote list
    shapes = json.loads(shapes_file.read_text())
    drawn = {f["properties"]["id"] for f in shapes["features"]}
    data["p"] = {k: v for k, v in data["p"].items() if k in drawn}      # a precinct with no shape cannot be clicked
    shapes["features"] = [f for f in shapes["features"] if f["properties"]["id"] in data["p"]]
    (dest / "precincts.json").write_text(json.dumps(data, separators=(",", ":")))
    # The vote-by-mail part of every row, in a separate file the site loads only for the vote-by-mail analyses.
    method = build(svc, columns, vbm=True)
    method["p"] = {k: v for k, v in method["p"].items() if k in data["p"]}
    if method["p"]:
        (dest / "precincts_method.json").write_text(json.dumps({"p": {k: v["v"] for k, v in method["p"].items()}}, separators=(",", ":")))
    else:
        (dest / "precincts_method.json").unlink(missing_ok=True)
    (dest / "precincts.geojson").write_text(json.dumps(shapes, separators=(",", ":")))
    (dest / "precincts_report.json").write_text(json.dumps({"precincts": len(data["p"]), "contests": len(data["names"]), "city_contests": report}, indent=1) + "\n")
    return f"precinct layer: {len(data['p'])} precincts with a shape, {len(columns)} contests with precinct votes" + (f"; city contests: {report['matched']} matched, {report['unmatched_header']} no title match, {report['refused_totals']} refused" if report else "")
