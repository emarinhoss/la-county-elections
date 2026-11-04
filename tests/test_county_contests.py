import json

from sitegen.county_contests import build


def write(path, header, rows):
    path.write_text(",".join(header) + "\n" + "\n".join(",".join(map(str, r)) for r in rows) + "\n")


def test_groups_ordered_cities_excluded_totals_from_latest(tmp_path):
    (tmp_path / "election.json").write_text(json.dumps({"title": "T", "date": "2026-11-03", "registered": 1000}))
    write(tmp_path / "contests.csv",
          ["contest_id", "group", "group_order", "title", "type", "vote_for", "pass_rate", "measure_text"], [
              [1, "County Measures", 11, "COUNTY MEASURE A", "Measure", "", "Majority of votes cast", "Shall we"],
              [2, "Governor", 2, "GOVERNOR", "Candidate", "", "", ""],
              [3, "Cities", 90, "CITY OF X GENERAL MUNICIPAL ELECTION Mayor", "Candidate", "", "", ""]])
    write(tmp_path / "choices.csv", ["contest_id", "choice_id", "name", "party"],
          [[1, 10, "YES", "Non Partisan"], [1, 11, "NO", "Non Partisan"], [2, 12, "A", "X"], [3, 13, "B", "Y"]])
    write(tmp_path / "results.csv", ["snapshot", "county_time", "choice_id", "votes"], [
        ["s1", "early", 10, 1], ["s2", "later", 10, 60], ["s2", "later", 11, 40], ["s2", "later", 12, 7], ["s2", "later", 13, 3]])
    write(tmp_path / "contest_counters.csv", ["snapshot", "county_time", "contest_id", "counter", "value"],
          [["s2", "later", 1, "CBLT", 100]])
    write(tmp_path / "election_counters.csv", ["snapshot", "county_time", "counter", "value"],
          [["s1", "early", "EBLT", 5], ["s2", "later", "EBLT", 250], ["s2", "later", "MBLT", 200]])
    out = build(tmp_path)
    assert [g["name"] for g in out["groups"]] == ["Governor", "County Measures"]  # sorted by county order, Cities left out
    measure = out["groups"][1]["contests"][0]
    assert measure["label"] == "County Measure A" and measure["measure_text"] == "Shall we"
    assert [c["share"] for c in measure["choices"]] == [0.6, 0.4]
    assert out["totals"] == {"registered": 1000, "ballots_counted": 250, "vote_by_mail_ballots": 200, "share_of_registered": 0.25}
