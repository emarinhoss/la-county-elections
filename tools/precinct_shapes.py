"""Precinct shapes for the map: only the precincts that appear in the county's SVC file, as small GeoJSON.

Input:  the polygons tools.precinct_geo downloaded (JSON list of features), and the pipeline's precinct_votes.csv.gz.
Output: GeoJSON with one feature per precinct, property "id" only. A precinct in the SVC with no polygon is listed in the
printed summary, not drawn. Coordinates are rounded to 5 decimals (about 1 metre) to keep the file small.

Usage: python -m tools.precinct_shapes <polygons.json> <precinct_votes.csv.gz> <out.geojson>
"""
import csv
import gzip
import json
import sys


def round_coords(c):
    return [round(c[0], 5), round(c[1], 5)] if isinstance(c[0], (int, float)) else [round_coords(x) for x in c]


def build(features, precinct_ids):
    """(GeoJSON dict, ids with no polygon). Features keep the order of the layer."""
    want = set(precinct_ids)
    out, seen = [], set()
    for f in features:
        pid = f["properties"]["PRECINCT"]
        if pid in want and f.get("geometry"):
            g = f["geometry"]
            out.append({"type": "Feature", "properties": {"id": pid}, "geometry": {"type": g["type"], "coordinates": round_coords(g["coordinates"])}})
            seen.add(pid)
    return {"type": "FeatureCollection", "features": out}, sorted(want - seen)


def precinct_ids(votes_csv_gz):
    with gzip.open(votes_csv_gz, "rt", newline="") as f:
        return {r["precinct"] for r in csv.DictReader(f)}


if __name__ == "__main__":
    polys, votes, dest = sys.argv[1:4]
    geojson, missing = build(json.load(open(polys)), precinct_ids(votes))
    with open(dest, "w") as f:
        json.dump(geojson, f, separators=(",", ":"))
    print(f"{len(geojson['features'])} precinct shapes written; {len(missing)} SVC precincts have no polygon: {missing[:10]}")
