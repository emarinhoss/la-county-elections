"""Find each precinct's city from its SHAPE, using the county precinct layer and the county city-boundary layer.

A precinct is assigned to the city polygon that covers the largest share of it. If no city covers at least half of it,
it is unincorporated (blank city). This does not depend on contest titles, city codes or place names, so it is the
reference the other signals are checked against.

Output CSV: PRECINCT, city (blank = unincorporated), overlap_share (share of the precinct inside that city; 0 if none).
Areas are computed in degrees, which is fine for a share of one small polygon inside another.

Usage: python -m tools.precinct_geo <boundary_geojson> <out_csv>
"""
import csv
import json
import sys
import urllib.parse
import urllib.request

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

LAYER = "https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/Registrar_Recorder_Precincts/FeatureServer/0/query"
PAGE = 1000
MIN_SHARE = 0.5
USER_AGENT = "la-county-elections-collector (public research project)"


def query_url(extra):
    params = {"where": "1=1", "f": "geojson", **extra}
    return LAYER + "?" + urllib.parse.urlencode(params)


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def download_polygons(get=http_json, max_pages=200):
    """All precinct features (PRECINCT + geometry in WGS84), paged and checked against the layer's own count."""
    expected = get(query_url({"returnCountOnly": "true", "f": "json"}))["count"]
    feats = []
    for page in range(max_pages):
        data = get(query_url({"outFields": "PRECINCT", "outSR": "4326", "geometryPrecision": "5", "maxAllowableOffset": "0.00005",
                              "orderByFields": "OBJECTID", "resultOffset": page * PAGE, "resultRecordCount": PAGE}))
        got = data.get("features", [])
        feats += got
        if len(got) < PAGE and not data.get("exceededTransferLimit"):
            break
    ids = [f["properties"]["PRECINCT"] for f in feats]
    if len(feats) != expected or len(set(ids)) != len(ids):
        raise SystemExit(f"got {len(feats)} polygons ({len(set(ids))} distinct ids) but the layer reports {expected}")
    return feats


def city_polygons(boundary_geojson):
    """{city name: geometry} for incorporated cities (a city can be several pieces)."""
    data = json.loads(open(boundary_geojson).read())
    pieces = {}
    for f in data["features"]:
        p = f["properties"]
        if p.get("CITY_TYPE") == "City" and f.get("geometry"):
            pieces.setdefault(p["CITY_NAME"], []).append(shape(f["geometry"]).buffer(0))
    return {name: unary_union(g) for name, g in pieces.items()}


def assign_cities(features, cities):
    """[(precinct, city or '', overlap_share)] using the largest-overlap rule."""
    names = list(cities)
    geoms = [cities[n] for n in names]
    tree = STRtree(geoms)
    out = []
    for f in features:
        poly = shape(f["geometry"])
        if not poly.is_valid:
            poly = poly.buffer(0)
        area = poly.area
        best, best_share = "", 0.0
        if area > 0:
            for i in tree.query(poly, predicate="intersects"):
                share = poly.intersection(geoms[i]).area / area
                if share > best_share:
                    best, best_share = names[i], share
        if best_share < MIN_SHARE:
            best = ""
        out.append((f["properties"]["PRECINCT"], best, round(best_share if best else 0.0, 4)))
    return out


if __name__ == "__main__":
    boundary, out_csv = sys.argv[1:3]
    rows = assign_cities(download_polygons(), city_polygons(boundary))
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["PRECINCT", "city", "overlap_share"])
        w.writerows(rows)
    inc = sum(1 for r in rows if not r[1])
    print(f"{len(rows)} precincts: {len(rows) - inc} in a city, {inc} unincorporated or mostly outside any city")
