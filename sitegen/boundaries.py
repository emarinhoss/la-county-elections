"""Join the county city-boundary polygons to the city contests.

Input:  latest data/raw/<election>/city_boundary_geojson snapshot, site/data/city_contests.json
Output: site/data/city_boundaries.geojson  (properties: name, key, kind, has_contests)
        site/data/boundary_report.json     (which names did not match, in either direction)

The layer's field names are not verified yet, so we look for the city name in a short list of
likely fields and stop with a clear message if none is found.
"""
import json
import sys
from pathlib import Path

from sitegen.city_contests import city_key

NAME_FIELDS = ["CITY_NAME", "CITY", "NAME", "City", "Name"]
TYPE_FIELDS = ["CITY_TYPE", "TYPE", "FEAT_TYPE"]


def pick(props, fields):
    for f in fields:
        if props.get(f):
            return str(props[f]).strip()
    return None


def join(geojson, contest_keys):
    """Return (output geojson, report). Raises if no feature has a usable name."""
    features, boundary_keys = [], set()
    for ft in geojson.get("features", []):
        props = ft.get("properties") or {}
        name = pick(props, NAME_FIELDS)
        if not name or not ft.get("geometry"):
            continue
        kind = (pick(props, TYPE_FIELDS) or "").lower()
        key = city_key(name)
        boundary_keys.add(key)
        features.append({
            "type": "Feature", "geometry": ft["geometry"],
            "properties": {"name": name, "key": key, "kind": kind, "has_contests": key in contest_keys},
        })
    if not features:
        first = (geojson.get("features") or [{}])[0].get("properties", {})
        raise SystemExit(f"no feature had a name in {NAME_FIELDS}; fields present: {sorted(first)}")
    report = {
        "polygons": len(features),
        "cities_with_contests_but_no_polygon": sorted(contest_keys - boundary_keys),
        "polygons_with_contests": sum(f["properties"]["has_contests"] for f in features),
    }
    return {"type": "FeatureCollection", "features": features}, report


def latest_body(source_dir):
    snaps = sorted(p for p in Path(source_dir).iterdir() if (p / "body").exists())
    return snaps[-1] / "body"


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    src = Path(f"data/raw/{election}/city_boundary_geojson")
    if not src.exists():
        print("no boundary snapshot yet: map will list cities without shapes")
        sys.exit(0)
    contests = json.loads(Path("site/data/city_contests.json").read_text())
    keys = {c["key"] for c in contests["cities"]}
    out, report = join(json.loads(latest_body(src).read_text()), keys)
    Path("site/data/city_boundaries.geojson").write_text(json.dumps(out, separators=(",", ":")))
    Path("site/data/boundary_report.json").write_text(json.dumps(report, indent=1) + "\n")
    print(report)
