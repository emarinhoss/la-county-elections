from sitegen.history import build, county_iso


def write(path, header, rows):
    path.write_text(",".join(header) + "\n" + "\n".join(",".join(map(str, r)) for r in rows) + "\n")


def test_county_iso():
    assert county_iso("11/4/2026 3:11:55 AM") == "2026-11-04T03:11:55"
    assert county_iso("11/6/2026 4:05:00 PM") == "2026-11-06T16:05:00"
    assert county_iso("not a time") is None


def test_series_follow_snapshot_order_and_missing_is_null(tmp_path):
    write(tmp_path / "results.csv", ["snapshot", "county_time", "choice_id", "votes"], [
        ["b", "11/5/2026 9:00:00 AM", 1, 70], ["b", "11/5/2026 9:00:00 AM", 2, 30], ["b", "11/5/2026 9:00:00 AM", 3, 5],
        ["a", "11/4/2026 3:11:55 AM", 1, 60], ["a", "11/4/2026 3:11:55 AM", 2, 40]])  # choice 3 absent in tally a
    write(tmp_path / "choices.csv", ["contest_id", "choice_id", "name", "party"],
          [[9, 1, "YES", "NP"], [9, 2, "NO", "NP"], [9, 3, "MAYBE", "NP"]])
    write(tmp_path / "contest_counters.csv", ["snapshot", "county_time", "contest_id", "counter", "value"],
          [["a", "t", 9, "CBLT", 100], ["b", "t", 9, "CBLT", 105], ["b", "t", 9, "CUV", 7]])
    write(tmp_path / "election_counters.csv", ["snapshot", "county_time", "counter", "value"],
          [["a", "t", "EBLT", 1000], ["b", "t", "EBLT", 1500]])
    out = build(tmp_path)
    assert [t["snapshot"] for t in out["times"]] == ["a", "b"]
    assert out["times"][1]["county_iso"] == "2026-11-05T09:00:00"
    c = out["contests"]["9"]
    assert {x["name"]: x["votes"] for x in c["choices"]} == {"YES": [60, 70], "NO": [40, 30], "MAYBE": [None, 5]}
    assert c["ballots"] == [100, 105] and out["ballots_counted"] == [1000, 1500]


def test_repeated_identical_tallies_are_dropped_but_real_changes_stay(tmp_path):
    t = "11/4/2026 3:11:55 AM"
    write(tmp_path / "results.csv", ["snapshot", "county_time", "choice_id", "votes"], [
        ["a", t, 1, 60], ["a", t, 2, 40],
        ["b", t, 1, 60], ["b", t, 2, 40],            # same tally served again
        ["c", "11/5/2026 9:00:00 AM", 1, 70], ["c", "11/5/2026 9:00:00 AM", 2, 45],
        ["d", t, 1, 60], ["d", t, 2, 40]])           # differs from c, so it is kept
    write(tmp_path / "choices.csv", ["contest_id", "choice_id", "name", "party"], [[9, 1, "YES", "NP"], [9, 2, "NO", "NP"]])
    write(tmp_path / "contest_counters.csv", ["snapshot", "county_time", "contest_id", "counter", "value"],
          [["a", t, 9, "CBLT", 100], ["b", t, 9, "CBLT", 100], ["c", "x", 9, "CBLT", 130], ["d", t, 9, "CBLT", 100]])  # includes dropped snapshot b
    write(tmp_path / "election_counters.csv", ["snapshot", "county_time", "counter", "value"],
          [["a", t, "EBLT", 1000], ["b", t, "EBLT", 1000], ["c", "x", "EBLT", 1300], ["d", t, "EBLT", 1000]])
    out = build(tmp_path)
    assert [x["snapshot"] for x in out["times"]] == ["a", "c", "d"]
    assert out["ballots_counted"] == [1000, 1300, 1000] and out["contests"]["9"]["ballots"] == [100, 130, 100]
