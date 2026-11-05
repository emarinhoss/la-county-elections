import csv
import json

from sitegen.city_totals import build, find_svc_dir, match_columns


def write(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def make_api(tmp):
    tidy = tmp / "tidy"
    tidy.mkdir()
    (tidy / "election.json").write_text(json.dumps({"election_id": 4348, "title": "T", "date": "2026-11-03", "registered": 1}))
    write(tidy / "contests.csv", ["contest_id", "group", "group_order", "title", "type", "vote_for", "pass_rate", "measure_text"], [
        [1, "County Measures", 11, "COUNTY MEASURE G", "Measure", "", "", ""],
        [2, "Governor", 2, "GOVERNOR", "Candidate", "", "", ""],
        [3, "State Measures", 15, "STATE MEASURE 5", "Measure", "", "", ""],
        [4, "State Senator", 8, "STATE SENATOR, 35th District", "Candidate", "", "", ""],
        [5, "Cities", 90, "CITY OF X GENERAL MUNICIPAL ELECTION Mayor", "Candidate", "", "", ""]])
    write(tidy / "choices.csv", ["contest_id", "choice_id", "name", "party"], [
        [1, 10, "YES", "NP"], [1, 11, "NO", "NP"], [2, 20, "A", "Democratic"], [2, 21, "B", "Republican"],
        [3, 30, "YES", "NP"], [3, 31, "NO", "NP"], [4, 40, "C", "X"], [4, 41, "D", "Y"], [5, 50, "E", "NP"]])
    write(tidy / "results.csv", ["snapshot", "county_time", "choice_id", "votes"], [
        ["s", "11/5/2026 9:00:00 AM", 10, 100], ["s", "t", 11, 60], ["s", "t", 20, 70], ["s", "t", 21, 90],
        ["s", "t", 30, 50], ["s", "t", 31, 50], ["s", "t", 40, 12], ["s", "t", 41, 8], ["s", "t", 50, 3]])
    write(tidy / "contest_counters.csv", ["snapshot", "county_time", "contest_id", "counter", "value"], [["s", "t", 1, "CBLT", 1]])
    return tidy


def make_svc(tmp):
    svc = tmp / "svc"
    svc.mkdir()
    write(svc / "countywide_checks.csv", ["seq", "title", "choices", "printed_votes", "summed_votes", "votes_match_printed", "share_fallback"], [
        [1, "COUNTY MEASURE G", 2, "[100, 60]", "[100, 60]", True, 0],
        [2, "GOVERNOR", 2, "[90, 70]", "[90, 70]", True, 0],                       # columns are in the opposite order to the API
        [3, "STATE MEASURE 5", 2, "[50, 50]", "[50, 50]", True, 0],                # equal non-zero totals: cannot be told apart
        [4, "Voter Nominated : STATE SENATOR, 35th District", 2, "[11, 8]", "[11, 8]", True, 0],  # the count has moved on: 11 vs the API's 12
        [5, "SOMETHING THE API DOES NOT HAVE", 2, "[1, 1]", "[1, 1]", True, 0]])
    cols = ["seq", "title", "city", "precincts", "registration", "ballots", "ballots_geo", "ballots_fallback", "choice_1", "choice_2"]
    def rows(seq, title, data):
        return [[seq, title, city, 1, reg, ballots, ballots - fb, fb, c1, c2] for city, reg, ballots, fb, c1, c2 in data]
    write(svc / "countywide_by_city.csv", cols,
          rows(1, "COUNTY MEASURE G", [("Carson", 100, 55, 0, 30, 20), ("Los Angeles", 200, 70, 5, 40, 25), ("UNINCORPORATED: LENNOX", 50, 33, 0, 20, 10),
                                       ("UNINCORPORATED: WEST ATHENS", 40, 9, 0, 5, 3), ("UNASSIGNED: ALTADENA", 10, 8, 8, 5, 2)])
          + rows(2, "GOVERNOR", [("Carson", 100, 55, 0, 30, 20), ("Los Angeles", 200, 80, 0, 60, 50)])
          + rows(3, "STATE MEASURE 5", [("Carson", 100, 55, 0, 50, 50)])
          + rows(4, "Voter Nominated : STATE SENATOR, 35th District", [("Carson", 100, 55, 0, 11, 8)])
          + rows(5, "SOMETHING THE API DOES NOT HAVE", [("Carson", 100, 2, 0, 1, 1)]))
    return svc


def test_match_columns_by_total_not_by_order():
    assert match_columns([90, 70], [70, 90]) == ([1, 0], "ok")
    assert match_columns([100, 60], [100, 60]) == ([0, 1], "ok")
    assert match_columns([11, 8], [12, 8]) == (None, "totals_differ")
    assert match_columns([50, 50], [50, 50]) == (None, "ambiguous_equal_totals")
    assert match_columns([0, 0, 7], [7, 0, 0]) == ([1, 2, 0], "ok")  # equal zero totals are harmless: they take the zero choices in order


def test_build_joins_titles_and_columns_and_reports_what_it_refused(tmp_path):
    out, report = build(make_svc(tmp_path), make_api(tmp_path))
    assert out["available"] is True and [c["label"] for c in out["contests"]] == ["COUNTY MEASURE G", "GOVERNOR"]
    assert report["unmatched_svc_titles"] == ["SOMETHING THE API DOES NOT HAVE"]
    reasons = {r["title"]: r["reason"] for r in report["refused"]}
    assert reasons == {"STATE MEASURE 5": "ambiguous_equal_totals", "Voter Nominated : STATE SENATOR, 35th District": "totals_differ"}

    g = next(c for c in out["contests"] if c["label"] == "GOVERNOR")
    assert [c["name"] for c in g["choices"]] == ["A", "B"] and g["columns_in_api_order"] is False
    assert g["cities"]["carson"]["votes"] == [20, 30]  # column 1 (total 90) belongs to B, column 2 (total 70) to A
    assert g["cities"]["losangeles"]["votes"] == [50, 60]


def test_unincorporated_is_summed_and_unassigned_is_only_counted(tmp_path):
    out, _ = build(make_svc(tmp_path), make_api(tmp_path))
    m = next(c for c in out["contests"] if c["label"] == "COUNTY MEASURE G")
    assert set(m["cities"]) == {"carson", "losangeles", "unincorporated"}
    assert m["cities"]["unincorporated"]["votes"] == [25, 13] and m["cities"]["unincorporated"]["name"] == "Unincorporated areas"
    assert m["cities"]["unincorporated"]["ballots"] == 42 and m["cities"]["losangeles"]["fallback_ballots"] == 5
    assert m["unassigned_ballots"] == 8 and m["votes_not_in_a_city_or_unincorporated"] == [5, 2]
    # every vote is accounted for: cities + unincorporated + the unassigned place equal the county total
    in_places = [sum(c["votes"][j] for c in m["cities"].values()) for j in range(2)]
    assert [a + b for a, b in zip(in_places, m["votes_not_in_a_city_or_unincorporated"])] == [c["county_votes"] for c in m["choices"]]


def test_find_svc_dir_uses_the_election_id(tmp_path):
    tidy = make_api(tmp_path)
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") is None
    d = tmp_path / "rehearsal" / "4348_final_svc_precinct_public"
    d.mkdir(parents=True)
    (d / "countywide_checks.csv").write_text("seq\n")
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") == d
    other = tmp_path / "rehearsal" / "4348_semifinal_svc_precinct_v2"  # a differently named file is found too, "final" preferred
    other.mkdir()
    (other / "countywide_checks.csv").write_text("seq\n")
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") == d
    (d / "countywide_checks.csv").unlink()
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") == other
    assert find_svc_dir(tidy, root=tmp_path / "no such folder") is None
