"""Shapes for the map from the county's CONSOLIDATED election precincts layer (the precincts the SVC reports).

The layer "Registrar_Recorder_Precincts_Election" has one polygon per consolidated precinct (field Precinct, ids like 6220036A),
which is the unit of the Statement of Votes Cast. (The older layer we first used holds the regular "established" precincts, which
the county says are not for reporting results.) This tool:
  1. downloads every polygon, paged and checked against the layer's own count;
  2. checks every SVC precinct id against it and reports misses (with ballots) and layer-only precincts;
  3. writes data/rehearsal/<name>/precinct_shapes.geojson with only the polygons whose id is in the SVC (property "id");
  4. derives each precinct's city from its consolidated shape (the smallest city covering at least half of it, as in
     tools.precinct_geo) and lists the precincts whose city differs from the one the pipeline used before.

Usage: python -m tools.election_precincts <boundary_geojson> <out_dir>      (out_dir holds precinct_votes.csv.gz, precinct_city.csv)
"""
import csv
import gzip
import json
import sys
import urllib.parse
from pathlib import Path

from tools.precinct_geo import assign_cities, city_polygons, http_json
from tools.precinct_shapes import round_coords

LAYER = "https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/Registrar_Recorder_Precincts_Election/FeatureServer/0/query"
PAGE = 1000


def query_url(extra):
    return LAYER + "?" + urllib.parse.urlencode({"where": "1=1", "f": "geojson", **extra})


def download(get=http_json, max_pages=50):
    """All features with properties {"PRECINCT": id}; refuses a download whose size or ids disagree with the layer."""
    expected = get(query_url({"returnCountOnly": "true", "f": "json"}))["count"]
    feats = []
    for page in range(max_pages):
        data = get(query_url({"outFields": "Precinct", "outSR": "4326", "geometryPrecision": "5", "maxAllowableOffset": "0.00005",
                              "orderByFields": "OBJECTID", "resultOffset": page * PAGE, "resultRecordCount": PAGE}))
        got = data.get("features", [])
        feats += [{"type": "Feature", "properties": {"PRECINCT": f["properties"]["Precinct"]}, "geometry": f.get("geometry")} for f in got]
        if len(got) < PAGE and not data.get("exceededTransferLimit"):
            break
    ids = [f["properties"]["PRECINCT"] for f in feats]
    if len(feats) != expected or len(set(ids)) != len(ids):
        raise SystemExit(f"got {len(feats)} polygons ({len(set(ids))} distinct ids) but the layer reports {expected}")
    return feats


def svc_ballots(votes_csv_gz):
    """{precinct id: ballots in the first contest that lists it}: enough to weigh misses."""
    out = {}
    with gzip.open(votes_csv_gz, "rt", newline="") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["precinct"], int(r["ballots"]))
    return out


def match_report(svc, layer_ids):
    matched = sorted(set(svc) & set(layer_ids))
    missing = sorted(set(svc) - set(layer_ids))
    return {"svc_precincts": len(svc), "layer_precincts": len(set(layer_ids)), "matched": len(matched),
            "matched_share": round(len(matched) / len(svc), 4) if svc else None,
            "unmatched_svc": [{"precinct": p, "ballots": svc[p]} for p in missing],
            "unmatched_ballots": sum(svc[p] for p in missing), "layer_only": len(set(layer_ids) - set(svc))}


def city_changes(feats, svc, cities, old_city_csv):
    """(new assignment rows, rows whose city changed). A blank city means unincorporated."""
    old = {}
    with open(old_city_csv, newline="") as f:
        for r in csv.DictReader(f):
            c = r["city"]
            old[r["precinct"]] = "" if c.startswith("UNINCORPORATED: ") else c
    new = assign_cities([f for f in feats if f["properties"]["PRECINCT"] in svc], cities)
    changed = [{"precinct": p, "old_city": old.get(p, "(no earlier assignment)"), "new_city": c, "ballots": svc[p]} for p, c, _ in new if p in old and old[p] != c]
    return new, changed


if __name__ == "__main__":
    boundary, out_dir = sys.argv[1], Path(sys.argv[2])
    svc = svc_ballots(out_dir / "precinct_votes.csv.gz")
    feats = download()
    report = match_report(svc, [f["properties"]["PRECINCT"] for f in feats])
    keep = [{"type": "Feature", "properties": {"id": f["properties"]["PRECINCT"]}, "geometry": {"type": f["geometry"]["type"], "coordinates": round_coords(f["geometry"]["coordinates"])}}
            for f in feats if f["properties"]["PRECINCT"] in svc and f.get("geometry")]
    (out_dir / "precinct_shapes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": keep}, separators=(",", ":")))
    new, changed = city_changes(feats, svc, city_polygons(boundary), out_dir / "precinct_city.csv")
    with open(out_dir / "city_change_consolidated.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["precinct", "old_city", "new_city", "ballots"])
        w.writeheader()
        w.writerows(changed)
    report["city_changed_precincts"] = len(changed)
    report["city_changed_ballots"] = sum(c["ballots"] for c in changed)
    report["total_ballots"] = sum(svc.values())
    report["shapes_written"] = len(keep)
    (out_dir / "election_layer_match.json").write_text(json.dumps(report, indent=1) + "\n")
    print(f"matched {report['matched']}/{report['svc_precincts']} SVC precincts ({report['matched_share']}); {len(report['unmatched_svc'])} unmatched "
          f"({report['unmatched_ballots']} ballots); layer-only {report['layer_only']}; shapes written {len(keep)}; "
          f"city changed for {len(changed)} precincts ({report['city_changed_ballots']} of {report['total_ballots']} ballots in first-listed contests)")
