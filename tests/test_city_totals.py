import csv
import json

from sitegen.city_totals import api_structure, build, find_svc_dir, header_score, match_columns, match_contest, pick_tally, saved_tallies


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
        [5, "Cities", 90, "CITY OF X GENERAL MUNICIPAL ELECTION Mayor", "Candidate", "", "", ""],
        [6, "State Measures", 15, "STATE MEASURE 1", "Measure", "", "", ""],
        [7, "State Measures", 15, "STATE MEASURE 10", "Measure", "", "", ""],
        [8, "Supreme Court Justices", 16, "For Associate Justice of the Supreme Court - JOSHUA GROBAN", "Judicial", "", "", ""]])
    write(tidy / "choices.csv", ["contest_id", "choice_id", "name", "party"], [
        [1, 10, "YES", "NP"], [1, 11, "NO", "NP"], [2, 20, "A", "Democratic"], [2, 21, "B", "Republican"],
        [3, 30, "YES", "NP"], [3, 31, "NO", "NP"], [4, 40, "C", "X"], [4, 41, "D", "Y"], [5, 50, "E", "NP"],
        [6, 60, "YES", "NP"], [6, 61, "NO", "NP"], [7, 70, "YES", "NP"], [7, 71, "NO", "NP"], [8, 80, "YES", "NP"], [8, 81, "NO", "NP"]])
    votes = {10: 100000, 11: 60000, 20: 70000, 21: 90000, 30: 50000, 31: 50000, 40: 12000, 41: 8000, 50: 3000,
             60: 30000, 61: 20000, 70: 5000, 71: 9000, 80: 80000, 81: 20000}
    write(tidy / "results.csv", ["snapshot", "county_time", "choice_id", "votes"],
          [["s", "11/5/2026 9:00:00 AM" if cid == 10 else "t", cid, v] for cid, v in votes.items()])
    write(tidy / "contest_counters.csv", ["snapshot", "county_time", "contest_id", "counter", "value"], [["s", "t", 1, "CBLT", 1]])
    return tidy


GOV_HEADER = "Voter Nominated : GOVERNOR SOMEONE SOMEBODY"
RET_HEADER = ("For Associate Justice of the Supreme Court Shall Associate Justice of the Supreme Court JOSHUA GROBAN be elected "
              "Los Angeles County Results Only to the office for the term provided by law?")


def make_svc(tmp):
    svc = tmp / "svc"
    svc.mkdir()
    status = "SEMIFINAL OFFICIAL CANVASS V2"
    write(svc / "countywide_checks.csv", ["seq", "title", "header", "status", "choices", "printed_votes", "summed_votes", "votes_match_printed", "share_fallback"], [
        [1, "COUNTY MEASURE G", "COUNTY MEASURE G", status, 2, "[100000, 60000]", "", True, 0],
        [2, "Voter Nominated :", GOV_HEADER, status, 2, "[90000, 70000]", "", True, 0],          # title on the next line; columns in the opposite order
        [3, "STATE MEASURE 5", "Los Angeles County Results Only STATE MEASURE 5", status, 2, "[50000, 50000]", "", True, 0],  # cannot be told apart
        [4, "Voter Nominated :", "Voter Nominated : STATE SENATOR, 35th District C D", status, 2, "[11000, 8000]", "", True, 0],  # 8% off: not this tally
        [5, "SOMETHING THE API DOES NOT HAVE", "SOMETHING THE API DOES NOT HAVE", status, 2, "[1000, 1000]", "", True, 0],
        [6, "Los Angeles County Results Only STATE MEASURE 1", "Los Angeles County Results Only STATE MEASURE 1", status, 2, "[29990, 19995]", "", True, 0],  # a moment earlier
        [7, "Los Angeles County Results Only STATE MEASURE 10", "Los Angeles County Results Only STATE MEASURE 10", status, 2, "[5000, 9000]", "", True, 0],
        [8, "For Associate Justice of the Supreme Court Shall Associate", RET_HEADER, status, 2, "[80000, 20000]", "", True, 0]])
    cols = ["seq", "title", "city", "precincts", "registration", "ballots", "ballots_geo", "ballots_fallback", "choice_1", "choice_2"]

    def rows(seq, title, data):
        return [[seq, title, city, 1, reg, ballots, ballots - fb, fb, c1, c2] for city, reg, ballots, fb, c1, c2 in data]
    carson = [("Carson", 100000, 55000, 0, 30000, 20000)]
    write(svc / "countywide_by_city.csv", cols,
          rows(1, "COUNTY MEASURE G", [("Carson", 100000, 55000, 0, 30000, 20000), ("Los Angeles", 200000, 70000, 5000, 40000, 25000),
                                       ("UNINCORPORATED: LENNOX", 50000, 33000, 0, 20000, 10000), ("UNINCORPORATED: WEST ATHENS", 40000, 9000, 0, 5000, 3000),
                                       ("UNASSIGNED: ALTADENA", 10000, 8000, 8000, 5000, 2000)])
          + rows(2, "Voter Nominated :", [("Carson", 100000, 55000, 0, 30000, 20000), ("Los Angeles", 200000, 80000, 0, 60000, 50000)])  # column 1 = B's
          + rows(3, "STATE MEASURE 5", carson) + rows(4, "Voter Nominated :", carson) + rows(5, "SOMETHING", carson)
          + rows(6, "STATE MEASURE 1", [("Carson", 100000, 55000, 0, 29990, 19995)]) + rows(7, "STATE MEASURE 10", [("Carson", 100000, 55000, 0, 5000, 9000)])
          + rows(8, "retention", [("Carson", 100000, 55000, 0, 80000, 20000)]))
    return svc


def test_match_columns_exact_by_total_not_by_order():
    assert match_columns([90, 70], [70, 90]) == ([1, 0], "ok", 0.0)
    assert match_columns([100000, 60000], [100000, 60000]) == ([0, 1], "ok", 0.0)
    assert match_columns([0, 0, 7], [7, 0, 0]) == ([1, 2, 0], "ok", 0.0)  # equal zero totals are harmless: they take the zero choices in order
    assert match_columns([50000, 50000], [50000, 50000])[:2] == (None, "ambiguous")  # equal non-zero totals cannot be told apart


def test_match_columns_approximate_uses_the_real_sheriff_numbers_and_refuses_what_could_be_swapped():
    # real 2026 values: the county's file vs our saved 3:11:55 AM tally, about 0.05% apart
    mapping, status, gap = match_columns([1330305, 610722], [611041, 1330743])
    assert (mapping, status) == ([1, 0], "ok_approximate") and 0.0004 < gap < 0.0006
    assert match_columns([100000, 60000], [112000, 60000])[:2] == (None, "totals_differ")  # 11% off is a different tally
    assert match_columns([1000, 995], [998, 997])[:2] == (None, "ambiguous")  # neighbours within the allowance could be swapped
    assert match_columns([11, 8], [12, 8])[:2] == (None, "ambiguous")  # tiny totals: too close to call
    assert match_columns([5, 5, 5], [5, 5])[:2] == (None, "totals_differ")  # different number of choices


def test_header_matching_is_whole_word_and_handles_the_2026_layouts(tmp_path):
    api, _ = __import__("sitegen.city_totals", fromlist=["api_contests"]).api_contests(api_structure(make_api(tmp_path)), {})
    pick = lambda h: (match_contest(api, h)[0] or {}).get("title")
    assert pick(GOV_HEADER) == "GOVERNOR"                                               # "Voter Nominated :" on its own line
    assert pick("Los Angeles County Results Only STATE MEASURE 1") == "STATE MEASURE 1"  # not "STATE MEASURE 10"
    assert pick("Los Angeles County Results Only STATE MEASURE 10") == "STATE MEASURE 10"
    assert pick(RET_HEADER) == "For Associate Justice of the Supreme Court - JOSHUA GROBAN"  # a retention question
    assert pick("For Associate Justice of the Supreme Court Shall Associate Justice of the Supreme Court SOMEONE ELSE be elected") is None
    assert pick("nothing relevant here") is None
    assert header_score("STATE MEASURE 1", "STATE MEASURE 10") == 0


def test_build_joins_headers_and_columns_and_reports_what_it_refused(tmp_path):
    out, report = build(make_svc(tmp_path), make_api(tmp_path))
    assert out["available"] is True
    assert [c["label"] for c in out["contests"]] == ["COUNTY MEASURE G", "GOVERNOR", "STATE MEASURE 1", "STATE MEASURE 10",
                                                     "For Associate Justice of the Supreme Court - JOSHUA GROBAN"]
    assert [r["header"] for r in report["unmatched_svc_titles"]] == ["SOMETHING THE API DOES NOT HAVE"]
    assert {r["title"]: r["reason"] for r in report["refused"]} == {"STATE MEASURE 5": "ambiguous", "STATE SENATOR, 35th District": "totals_differ"}
    g = next(c for c in out["contests"] if c["label"] == "GOVERNOR")
    assert [c["name"] for c in g["choices"]] == ["A", "B"] and g["columns_in_api_order"] is False
    assert g["cities"]["carson"]["votes"] == [20000, 30000]  # column 1 (total 90000) belongs to B, column 2 (total 70000) to A
    m1 = next(c for c in out["contests"] if c["label"] == "STATE MEASURE 1")
    assert 0 < m1["difference_from_tally"] < 0.001 and out["tally"]["largest_difference"] == m1["difference_from_tally"]
    assert out["tally"]["svc_status"] == ["SEMIFINAL OFFICIAL CANVASS V2"] and report["tally"] == out["tally"]


def test_unincorporated_is_summed_and_unassigned_is_only_counted(tmp_path):
    out, _ = build(make_svc(tmp_path), make_api(tmp_path))
    m = next(c for c in out["contests"] if c["label"] == "COUNTY MEASURE G")
    assert set(m["cities"]) == {"carson", "losangeles", "unincorporated"}
    assert m["cities"]["unincorporated"]["votes"] == [25000, 13000] and m["cities"]["unincorporated"]["name"] == "Unincorporated areas"
    assert m["cities"]["unincorporated"]["ballots"] == 42000 and m["cities"]["losangeles"]["fallback_ballots"] == 5000
    assert m["unassigned_ballots"] == 8000 and m["votes_not_in_a_city_or_unincorporated"] == [5000, 2000]
    in_places = [sum(c["votes"][j] for c in m["cities"].values()) for j in range(2)]
    assert [a + b for a, b in zip(in_places, m["votes_not_in_a_city_or_unincorporated"])] == [c["county_votes"] for c in m["choices"]]


def add_later_tally(tidy, bump=10000):
    """A later tally in which every county total has moved on well past the tolerance (the live count passed the SVC file)."""
    rows = list(csv.reader(open(tidy / "results.csv")))[1:]
    write(tidy / "results.csv", ["snapshot", "county_time", "choice_id", "votes"],
          rows + [["s2", "11/6/2026 9:00:00 AM", r[2], int(r[3]) + bump] for r in rows])


def test_svc_is_matched_to_the_saved_tally_it_is_closest_to_not_just_the_latest(tmp_path):
    tidy, svc = make_api(tmp_path), make_svc(tmp_path)
    add_later_tally(tidy)  # the live feed has moved on: the SVC (cut from the earlier tally) must still be joined to it
    out, report = build(svc, tidy)
    t = out["tally"]
    assert t["snapshot"] == "s" and t["county_time"] == "11/5/2026 9:00:00 AM" and t["is_latest"] is False
    assert t["latest_county_time"] == "11/6/2026 9:00:00 AM" and t["svc_contests_matching_it"] == 5
    m = next(c for c in out["contests"] if c["label"] == "COUNTY MEASURE G")
    assert [c["county_votes"] for c in m["choices"]] == [100000, 60000]  # the matched tally's totals, consistent with the city sums


def test_ties_go_to_the_latest_tally_and_nothing_matching_includes_nothing(tmp_path):
    tidy, svc = make_api(tmp_path), make_svc(tmp_path)
    checks = list(csv.DictReader(open(svc / "countywide_checks.csv")))
    assert pick_tally(api_structure(tidy), saved_tallies(tidy), checks)[:2] == (5, "s")
    rows = list(csv.reader(open(tidy / "results.csv")))[1:]  # an identical copy saved later: the latest copy wins the tie
    write(tidy / "results.csv", ["snapshot", "county_time", "choice_id", "votes"], rows + [["s3", r[1], r[2], r[3]] for r in rows])
    assert pick_tally(api_structure(tidy), saved_tallies(tidy), checks)[:2] == (5, "s3")
    for chk in checks:  # an SVC that equals no saved tally at all
        chk["printed_votes"] = "[7000, 7]"
    assert pick_tally(api_structure(tidy), saved_tallies(tidy), checks)[0] == 0


def test_find_svc_dir_uses_the_election_id(tmp_path):
    tidy = make_api(tmp_path)
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") is None
    d = tmp_path / "rehearsal" / "4348_final_svc_precinct_public"
    d.mkdir(parents=True)
    (d / "countywide_checks.csv").write_text("seq\n")
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") == d
    other = tmp_path / "rehearsal" / "4348_semifinal_svc_precinct_v2"  # a differently named file is found too, whole-word "final" preferred
    other.mkdir()
    (other / "countywide_checks.csv").write_text("seq\n")
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") == d
    (d / "countywide_checks.csv").unlink()
    assert find_svc_dir(tidy, root=tmp_path / "rehearsal") == other
    assert find_svc_dir(tidy, root=tmp_path / "no such folder") is None
