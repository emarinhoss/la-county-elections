import csv
import gzip
import json

import pytest

from tools import election_precincts as ep

SQ = lambda x0, y0, x1, y1: {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def fake_get(features, count=None):
    def get(url):
        if "returnCountOnly" in url:
            return {"count": len(features) if count is None else count}
        off = int(url.split("resultOffset=")[1].split("&")[0])
        page = features[off:off + ep.PAGE]
        return {"features": [{"properties": {"Precinct": p}, "geometry": g} for p, g in page], "exceededTransferLimit": off + ep.PAGE < len(features)}
    return get


def test_download_pages_and_checks_the_count():
    feats = [(f"P{i:04d}A", SQ(0, 0, 1, 1)) for i in range(2500)]
    assert len(ep.download(fake_get(feats))) == 2500
    with pytest.raises(SystemExit):
        ep.download(fake_get(feats, count=2501))


def test_match_report_lists_misses_with_ballots():
    r = ep.match_report({"A": 10, "B": 20, "C": 5}, ["A", "C", "Z"])
    assert r["matched"] == 2 and r["unmatched_svc"] == [{"precinct": "B", "ballots": 20}] and r["unmatched_ballots"] == 20 and r["layer_only"] == 1


def test_city_changes(tmp_path):
    cities = {"Carson": __import__("shapely.geometry", fromlist=["shape"]).shape(SQ(0, 0, 10, 10))}
    feats = [{"properties": {"PRECINCT": "A"}, "geometry": SQ(1, 1, 2, 2)}, {"properties": {"PRECINCT": "B"}, "geometry": SQ(20, 20, 21, 21)}]
    old = tmp_path / "old.csv"
    with open(old, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["precinct", "city"])
        w.writerows([["A", "Carson"], ["B", "Carson"]])   # B was assigned to Carson from a fragment but its whole shape is outside
    new, changed = ep.city_changes(feats, {"A": 5, "B": 7}, cities, old)
    assert changed == [{"precinct": "B", "old_city": "Carson", "new_city": "", "ballots": 7}]
