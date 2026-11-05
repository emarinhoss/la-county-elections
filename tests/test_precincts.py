import csv
import gzip
import json

from sitegen import precincts
from tools.precinct_shapes import build as build_shapes


def make_svc(tmp_path):
    d = tmp_path / "svc"
    d.mkdir()
    with open(d / "precinct_city.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["precinct", "location", "city", "method", "share", "contest_city"])
        w.writerows([["1030003A", "CARSON", "Carson", "geo", 1, ""], ["3670013A", "LENNOX", "UNINCORPORATED: LENNOX", "geo_unincorporated", 0, ""]])
    with gzip.open(d / "precinct_votes.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "precinct", "registration", "ballots", "choice_1", "choice_2"])
        w.writerows([[5, "1030003A", 100, 30, 10, 20], [5, "3670013A", 80, 20, 15, 5], [6, "1030003A", 100, 30, 1, 2]])  # seq 6 not matched
    return d


def test_columns_are_put_in_api_order_and_unmatched_contests_dropped(tmp_path):
    d = make_svc(tmp_path)
    out = precincts.build(d, [("5", 777, [1, 0], 2)])   # SVC column 1 is API choice 2, column 2 is API choice 1
    assert out["p"]["1030003A"] == {"city": "carson", "v": {"777": [100, 30, 20, 10]}}
    assert out["p"]["3670013A"]["city"] == "unincorporated"
    assert list(out["p"]["1030003A"]["v"]) == ["777"]


def test_shapes_keep_only_precincts_with_votes_and_report_the_missing():
    feats = [{"properties": {"PRECINCT": "A"}, "geometry": {"type": "Polygon", "coordinates": [[[0.123456, 1.0], [1.0, 1.0], [0.0, 0.0], [0.123456, 1.0]]]}},
             {"properties": {"PRECINCT": "B"}, "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]
    gj, missing = build_shapes(feats, {"A", "C"})
    assert [f["properties"]["id"] for f in gj["features"]] == ["A"] and missing == ["C"]
    assert gj["features"][0]["geometry"]["coordinates"][0][0] == [0.12346, 1.0]


def test_not_available_without_shapes(tmp_path, monkeypatch):
    d = make_svc(tmp_path)
    monkeypatch.setattr(precincts, "SHAPES", tmp_path / "missing.geojson")
    dest = tmp_path / "site"
    dest.mkdir()
    assert "not available" in precincts.write_precincts(d, [("5", 777, [0, 1], 2)], dest)
    assert not (dest / "precincts.json").exists()
