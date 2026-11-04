import json

from sitegen.city_contests import build, city_key, parse_city_title, parse_vote_for


def test_title_patterns_seen_in_real_data():
    cases = {
        "CITY OF ALHAMBRA GENERAL MUNICIPAL ELECTION Member of the City Council, Fifth District":
            ("ALHAMBRA", "Member of the City Council, Fifth District"),
        "CITY OF ALHAMBRA SPECIAL MUNICIPAL ELECTION - MEASURE DB": ("ALHAMBRA", "MEASURE DB"),
        "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION Mayor": ("LOS ANGELES", "Mayor"),
        "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE EE": ("LOS ANGELES", "MEASURE EE"),
        "CITY OF PASADENA REGULAR MUNICIPAL ELECTION Mayor": ("PASADENA", "Mayor"),
        "CITY OF CULVER CITY GENERAL MUNICIPAL ELECTION Member of the City Council": ("CULVER CITY", "Member of the City Council"),
        "CITY OF LA VERNE GENERAL MUNICIPAL ELECTION City Clerk": ("LA VERNE", "City Clerk"),
    }
    for title, expected in cases.items():
        assert parse_city_title(title) == expected, title


def test_city_key_ignores_case_accents_spaces():
    assert city_key("La Cañada Flintridge") == city_key("LA CANADA  FLINTRIDGE") == "lacanadaflintridge"


def test_vote_for():
    assert parse_vote_for("") == 1
    assert parse_vote_for("Vote for no more than three") == 3


def write(path, header, rows):
    path.write_text(",".join(header) + "\n" + "\n".join(",".join(map(str, r)) for r in rows) + "\n")


def test_build_shares_use_latest_snapshot(tmp_path):
    (tmp_path / "election.json").write_text(json.dumps({"title": "T", "date": "2026-11-03"}))
    write(tmp_path / "contests.csv", ["contest_id", "group", "title", "type", "vote_for", "pass_rate"], [
        [1, "Cities", "CITY OF TESTVILLE SPECIAL MUNICIPAL ELECTION - MEASURE X", "Measure", "", "Majority of votes cast"],
        [2, "Governor", "GOVERNOR", "Candidate", "", ""],
    ])
    write(tmp_path / "choices.csv", ["contest_id", "choice_id", "name", "party"],
          [[1, 10, "YES", "Non Partisan"], [1, 11, "NO", "Non Partisan"], [2, 12, "A", "X"]])
    write(tmp_path / "results.csv", ["snapshot", "county_time", "choice_id", "votes"], [
        ["s1", "early", 10, 1], ["s1", "early", 11, 1], ["s1", "early", 12, 5],
        ["s2", "later", 10, 300], ["s2", "later", 11, 100], ["s2", "later", 12, 5]])
    write(tmp_path / "contest_counters.csv", ["snapshot", "county_time", "contest_id", "counter", "value"],
          [["s2", "later", 1, "CBLT", 410]])
    out = build(tmp_path)
    assert out["county_time"] == "later" and out["unparsed_titles"] == []
    assert [c["name"] for c in out["cities"]] == ["Testville"]
    contest = out["cities"][0]["contests"][0]
    assert contest["label"] == "MEASURE X" and contest["ballots_cast"] == 410
    assert [c["share"] for c in contest["choices"]] == [0.75, 0.25]
