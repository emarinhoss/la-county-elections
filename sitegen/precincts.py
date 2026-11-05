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

from sitegen.city_contests import city_key


def build(svc_dir, columns):
    svc = Path(svc_dir)
    where = {}
    for r in csv.DictReader(open(svc / "precinct_city.csv", newline="")):
        c = r["city"]
        where[r["precinct"]] = "" if c.startswith("UNASSIGNED: ") else "unincorporated" if c.startswith("UNINCORPORATED: ") else city_key(c)
    by_seq = {seq: (cid, mapping, n) for seq, cid, mapping, n in columns}
    precincts = defaultdict(lambda: {"city": "", "v": {}})
    with gzip.open(svc / "precinct_votes.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["seq"] not in by_seq:
                continue
            cid, mapping, n = by_seq[r["seq"]]
            votes = [0] * n
            for col, j in enumerate(mapping):
                votes[j] = int(r[f"choice_{col + 1}"])
            p = precincts[r["precinct"]]
            p["city"] = where.get(r["precinct"], "")
            p["v"][str(cid)] = [int(r["registration"]), int(r["ballots"]), *votes]
    return {"p": dict(precincts)}


# The shapes are the county's consolidated Election Precincts (the unit the SVC reports); tools/election_precincts.py checks that every
# SVC precinct id has a polygon and writes election_layer_match.json. Set to False to hide the layer without deleting anything.
PUBLISH = True


def write_precincts(svc_dir, columns, dest, publish=PUBLISH):
    dest = Path(dest)
    svc = Path(svc_dir)
    if not publish:
        for name in ("precincts.json", "precincts.geojson"):
            (dest / name).unlink(missing_ok=True)
        return "precinct layer switched off (PUBLISH is False)"
    shapes_file = svc / "precinct_shapes.geojson"
    if not (svc / "precinct_votes.csv.gz").exists() or not shapes_file.exists():
        for name in ("precincts.json", "precincts.geojson"):
            (dest / name).unlink(missing_ok=True)
        return "precinct layer not available yet (needs a svc-rehearsal run that saves precinct votes and shapes)"
    data = build(svc, columns)
    shapes = json.loads(shapes_file.read_text())
    drawn = {f["properties"]["id"] for f in shapes["features"]}
    data["p"] = {k: v for k, v in data["p"].items() if k in drawn}      # a precinct with no shape cannot be clicked
    shapes["features"] = [f for f in shapes["features"] if f["properties"]["id"] in data["p"]]
    (dest / "precincts.json").write_text(json.dumps(data, separators=(",", ":")))
    (dest / "precincts.geojson").write_text(json.dumps(shapes, separators=(",", ":")))
    return f"precinct layer: {len(data['p'])} precincts with a shape and votes in {len(columns)} countywide contests"
