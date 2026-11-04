import json
from pathlib import Path

from parse.election import check, parse_counters, parse_structure

FIX = Path(__file__).parent / "fixtures"
structure = json.loads((FIX / "election_data.json").read_text())
counters = json.loads((FIX / "counter_data.json").read_text())


def test_structure_has_expected_contests_and_choices():
    info, contests, choices = parse_structure(structure)
    assert info["election_id"] == 4348 and info["date"] == "2026-11-03"
    assert {c["title"] for c in contests} == {"COUNTY MEASURE A", "GOVERNOR"}
    measure = next(c for c in contests if c["title"] == "COUNTY MEASURE A")
    assert {c["name"] for c in choices if c["contest_id"] == measure["contest_id"]} == {"YES", "NO"}


def test_counters_split_by_type():
    results, ccount, ecount = parse_counters(counters, "snap1")
    assert {r["choice_id"] for r in results} == {c["choice_id"] for c in parse_structure(structure)[2]}
    assert {c["counter"] for c in ccount} == {"CBLT", "CUV", "COV"}
    assert {e["counter"] for e in ecount} == {"EBLT", "MBLT", "DBLT"}
    assert all(r["county_time"] == counters["TimeStamp"] for r in results)


def test_join_check_is_clean_and_catches_unknown_ids():
    _, contests, choices = parse_structure(structure)
    results, ccount, _ = parse_counters(counters, "s")
    assert check(contests, choices, results, ccount) == []
    results.append({"snapshot": "s", "county_time": "t", "choice_id": -1, "votes": 5})
    assert len(check(contests, choices, results, ccount)) == 1


def test_votes_match_the_source_numbers():
    results, _, _ = parse_counters(counters, "s")
    src = {r["ReferenceID"]: int(r["Value"]) for r in counters["Data"] if r["ReferenceType"] == "CAND"}
    assert {r["choice_id"]: r["votes"] for r in results} == src
