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
        w.writerow(["seq", "precinct", "registration", "ballots", "vbm_ballots", "choice_1", "choice_2", "vbm_choice_1", "vbm_choice_2"])
        w.writerows([[5, "1030003A", 100, 30, 18, 10, 20, 4, 14], [5, "3670013A", 80, 20, 12, 15, 5, 9, 3], [6, "1030003A", 100, 30, 20, 1, 2, 1, 1]])  # seq 6 not matched
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


def test_not_available_without_shapes(tmp_path):
    d = make_svc(tmp_path)
    dest = tmp_path / "site"
    dest.mkdir()
    assert "not available" in precincts.write_precincts(d, [("5", 777, [0, 1], 2)], dest, publish=True)
    assert not (dest / "precincts.json").exists()


def test_write_keeps_only_precincts_with_a_shape(tmp_path):
    d = make_svc(tmp_path)
    (d / "precinct_shapes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"id": "1030003A"}, "geometry": None}]}))
    dest = tmp_path / "site"
    dest.mkdir()
    assert "1 precincts" in precincts.write_precincts(d, [("5", 777, [0, 1], 2)], dest, publish=True)
    assert list(json.loads((dest / "precincts.json").read_text())["p"]) == ["1030003A"]


def test_can_be_switched_off(tmp_path):
    d = make_svc(tmp_path)
    (d / "precinct_shapes.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": []}))
    dest = tmp_path / "site"
    dest.mkdir()
    assert "switched off" in precincts.write_precincts(d, [("5", 777, [0, 1], 2)], dest, publish=False)
    assert not (dest / "precincts.json").exists()


def make_tidy(tmp_path):
    t = tmp_path / "tidy"
    t.mkdir()
    def w(name, fields, rows):
        with open(t / name, "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=fields)
            wr.writeheader()
            wr.writerows(rows)
    w("contests.csv", ["contest_id", "group", "group_order", "title", "type", "vote_for", "pass_rate", "measure_text"],
      [{"contest_id": 1, "group": "Cities", "group_order": 1, "title": "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION Mayor", "type": "Candidate", "vote_for": 1},
       {"contest_id": 2, "group": "Cities", "group_order": 1, "title": "CITY OF CARSON GENERAL MUNICIPAL ELECTION Mayor", "type": "Candidate", "vote_for": 1}])
    w("choices.csv", ["contest_id", "choice_id", "name", "party"],
      [{"contest_id": 1, "choice_id": 11, "name": "BASS", "party": ""}, {"contest_id": 1, "choice_id": 12, "name": "RAMAN", "party": ""},
       {"contest_id": 2, "choice_id": 21, "name": "SHARIF", "party": ""}, {"contest_id": 2, "choice_id": 22, "name": "SPICER", "party": ""}])
    w("results.csv", ["snapshot", "county_time", "choice_id", "votes"],
      [{"snapshot": "s1", "county_time": "t", "choice_id": c, "votes": v} for c, v in [(11, 700), (12, 300), (21, 90), (22, 60)]])
    return t


def test_city_contests_are_matched_by_title_and_totals(tmp_path):
    d = tmp_path / "svc"
    d.mkdir()
    rows = [
        {"seq": "5", "title": "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION Mayor", "header": "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION Mayor", "status": "S", "choices": 2,
         "printed_votes": "[300, 700]", "summed_votes": "[300, 700]", "votes_match_printed": True},                       # columns in the other order
        {"seq": "6", "title": "CITY OF CARSON GENERAL MUNICIPAL ELECTION Mayor", "header": "CITY OF CARSON GENERAL MUNICIPAL ELECTION Mayor", "status": "S", "choices": 2,
         "printed_votes": "[900, 10]", "summed_votes": "[900, 10]", "votes_match_printed": True},                         # totals disagree with the API: refused
        {"seq": "7", "title": "SOMEWHERE ELSE Mayor", "header": "SOMEWHERE ELSE Mayor", "status": "S", "choices": 2,
         "printed_votes": "[1, 2]", "summed_votes": "[1, 2]", "votes_match_printed": True},                                 # no API title: unmatched
        {"seq": "1", "title": "COUNTYWIDE", "header": "COUNTYWIDE", "status": "S", "choices": 2, "printed_votes": "[1, 2]", "summed_votes": "[1, 2]", "votes_match_printed": True},
    ]
    with open(d / "all_blocks_check.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    out, report = precincts.city_columns(d, make_tidy(tmp_path), "s1", {"1"})
    assert out == [("5", 1, [1, 0], 2, ["BASS", "RAMAN"])]
    assert report["city_blocks_seen"] == 3 and report["matched"] == 1 and report["unmatched_header"] == 1 and report["refused_totals"] == 1


def test_vote_by_mail_rows_are_in_api_order_and_missing_columns_are_skipped(tmp_path):
    d = make_svc(tmp_path)
    out = precincts.build(d, [("5", 777, [1, 0], 2)], vbm=True)       # SVC column 1 is API choice 2
    assert out["p"]["1030003A"]["v"]["777"] == [18, 14, 4] and out["p"]["3670013A"]["v"]["777"] == [12, 3, 9]
    old = tmp_path / "old"
    old.mkdir()
    (old / "precinct_city.csv").write_text((d / "precinct_city.csv").read_text())
    with gzip.open(old / "precinct_votes.csv.gz", "wt", newline="") as f:     # a file from before the vote-by-mail columns existed
        f.write("seq,precinct,registration,ballots,choice_1,choice_2\n5,1030003A,100,30,10,20\n")
    assert precincts.build(old, [("5", 777, [0, 1], 2)], vbm=True)["p"] == {}
