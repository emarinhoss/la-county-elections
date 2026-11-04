"""Download the attribute table (no shapes) of the county precinct layer, paging past the 2,000-row limit.

Output CSV columns: PRECINCT, CITY_EST, SUBCODE, DST_CITY. Checks that the row count equals the layer's own count.

Usage: python -m tools.arcgis_attrs <out_csv>
"""
import csv
import json
import sys
import urllib.parse
import urllib.request

LAYER = "https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/Registrar_Recorder_Precincts/FeatureServer/0/query"
FIELDS = ["PRECINCT", "CITY_EST", "SUBCODE", "DST_CITY"]
PAGE = 2000
USER_AGENT = "la-county-elections-collector (public research project)"


def query_url(extra):
    params = {"where": "1=1", "returnGeometry": "false", "f": "json", **extra}
    return LAYER + "?" + urllib.parse.urlencode(params)


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def download(get=http_json, max_pages=100):
    """Return a list of row dicts. `get` is injectable so tests need no network."""
    expected = get(query_url({"returnCountOnly": "true"}))["count"]
    rows = []
    for page in range(max_pages):
        data = get(query_url({"outFields": ",".join(FIELDS), "orderByFields": "OBJECTID",
                              "resultOffset": page * PAGE, "resultRecordCount": PAGE}))
        feats = data.get("features", [])
        rows += [{k: f["attributes"].get(k) for k in FIELDS} for f in feats]
        if not feats or not data.get("exceededTransferLimit"):
            break
    if len(rows) != expected:
        raise SystemExit(f"downloaded {len(rows)} rows but the layer reports {expected}")
    if len({r["PRECINCT"] for r in rows}) != len(rows):
        raise SystemExit("duplicate PRECINCT values in the layer")
    return rows


if __name__ == "__main__":
    out = sys.argv[1]
    rows = download()
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} precincts written to {out}")
