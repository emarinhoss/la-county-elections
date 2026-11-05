import csv
import json

from tools.svc_pipeline import (UNASSIGNED, UNINC, aggregate_by_city, assign_all, city_from_title, countywide_blocks,
                                geo_lookup, load_boundary_cities, load_geo, run)
from tools.svc_parse import parse


def make_svc_text(blocks):
    """Text in the same layout as the real county PDF (see tests/fixtures/svc and tools/svc_parse.py).
    blocks: [(seq, title, [(location, precinct, in_person, vbm, registration)])]; in_person/vbm = [ballots, votes...]"""
    out = []
    for seq, title, rows in blocks:
        out += [f"COUNTY OF LOS ANGELES      11/05/24    GENERAL ELECTION     {seq}.1   -Page- {seq}", "", f"   {title}", "", "FINAL OFFICIAL V2", ""]
        for loc, pid, ip, vbm, reg in rows:
            total = [a + b for a, b in zip(ip, vbm)]
            out += [f"{loc} - {pid}        " + "   ".join(map(str, ip)),
                    " VOTE BY MAIL        SERIAL 0001      " + "   ".join(map(str, vbm)),
                    f"TOTAL                 {reg}     " + "   ".join(map(str, total))]
        n = len(rows[0][2])
        pt = [sum(r[2][i] for r in rows) for i in range(n)]
        vt = [sum(r[3][i] for r in rows) for i in range(n)]
        out += ["PRECINCT TOTAL     " + "   ".join(map(str, pt)), "VBM TOTAL     " + "   ".join(map(str, vt)),
                f"GRAND TOTAL     {sum(r[4] for r in rows)}   " + "   ".join(str(a + b) for a, b in zip(pt, vt)), ""]
    return "\n".join(out)


ROW = ([10, 6, 4], [20, 12, 8], 100)  # in-person, vote-by-mail, registration; every precinct has the same numbers
CARSON_LISTED = [f"103000{i}A" for i in range(3, 8)]  # 5 precincts listed in Carson's own contest
ALL = [("CARSON", p, *ROW) for p in CARSON_LISTED] + [
    ("WEST CARSON", "1030008A", *ROW),   # shape is in Carson, but no city contest lists it
    ("CARSON", "1030009B", *ROW),        # id not in the layer, but the layer has 1030009A (Carson): base fallback
    ("SUNLAND", "6850002B", *ROW),       # shape in Los Angeles, listed in the Los Angeles measure
    ("LOMITA", "7000001A", *ROW),        # listed in the "Los Angeles" measure, but its SHAPE is in Lomita
    ("LOMITA", "7000002A", *ROW),        # shape in Lomita
    ("LENNOX", "3670013A", *ROW),        # shape in no city
    ("WEST ATHENS", "3670014A", *ROW),   # shape in no city
    ("LOS ANGELES", "9999999A", *ROW),   # not in the layer at all; place name is a city
]
BLOCKS = [
    (1, "CARSON CITY GENERAL MUNICIPAL ELECTION Mayor", [("CARSON", p, *ROW) for p in CARSON_LISTED]),
    (2, "COUNTY MEASURE G", ALL),
    (3, "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE LL", [("SUNLAND", "6850002B", *ROW), ("LOMITA", "7000001A", *ROW)]),
]
TEXT = make_svc_text(BLOCKS)
GEO_ROWS = ([(p, "Carson", 1.0) for p in CARSON_LISTED] + [("1030008A", "Carson", 0.95), ("1030009A", "Carson", 1.0),
            ("6850002B", "Los Angeles", 1.0), ("7000001A", "Lomita", 0.97), ("7000002A", "Lomita", 1.0),
            ("3670013A", "", 0.0), ("3670014A", "", 0.0)])


def write_inputs(tmp_path):
    geo = tmp_path / "geo.csv"
    with open(geo, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["PRECINCT", "city", "overlap_share"])
        w.writerows(GEO_ROWS)
    gj = tmp_path / "b.geojson"
    gj.write_text(json.dumps({"features": [{"properties": {"CITY_NAME": n, "CITY_TYPE": t}} for n, t in
                                           [("Carson", "City"), ("Los Angeles", "City"), ("Lomita", "City"),
                                            ("Culver City", "City"), ("Unincorporated", "Unincorporated")]]}))
    return geo, gj


def inputs(tmp_path):
    geo, gj = write_inputs(tmp_path)
    return load_geo(geo), load_boundary_cities(gj)


def test_generated_text_is_valid_for_the_parser():
    from tools.svc_parse import check_block
    for b in parse(TEXT):
        assert check_block(b) == ([], [])


def test_geo_lookup_exact_base_and_missing(tmp_path):
    geo, _ = inputs(tmp_path)
    assert geo_lookup("1030003A", geo) == ("Carson", 1.0, "exact")
    assert geo_lookup("3670013A", geo) == (None, 0.0, "exact")  # unincorporated
    assert geo_lookup("1030009B", geo) == ("Carson", None, "base")
    assert geo_lookup("9999999A", geo) is None


def test_base_fallback_is_refused_when_the_layer_disagrees_with_itself(tmp_path):
    geo_csv = tmp_path / "g.csv"
    geo_csv.write_text("PRECINCT,city,overlap_share\n5550001A,Alpha,1.0\n5550001B,Beta,1.0\n")
    assert geo_lookup("5550001C", load_geo(geo_csv)) is None


def test_city_from_title_handles_both_styles(tmp_path):
    _, boundary = inputs(tmp_path)
    assert city_from_title("CARSON CITY GENERAL MUNICIPAL ELECTION Mayor", boundary) == "Carson"
    assert city_from_title("LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE LL", boundary) == "Los Angeles"
    assert city_from_title("CITY OF CULVER CITY GENERAL MUNICIPAL ELECTION Mayor", boundary) == "Culver City"
    assert city_from_title("COUNTY MEASURE G", boundary) is None
    assert city_from_title("CITY OF NOWHERE GENERAL MUNICIPAL ELECTION Mayor", boundary) is None


def test_shape_decides_the_city_and_contest_titles_do_not(tmp_path):
    geo, boundary = inputs(tmp_path)
    table, diag = assign_all(list(parse(TEXT)), geo, boundary)
    got = {pid: (t["city"], t["method"]) for pid, t in table.items()}
    assert got["1030003A"] == ("Carson", "geo")
    assert got["1030008A"] == ("Carson", "geo")  # no contest lists it; the shape does
    assert got["1030009B"] == ("Carson", "geo_base")
    assert got["7000001A"] == ("Lomita", "geo")  # the Los Angeles measure lists it, but the shape is in Lomita
    assert got["3670013A"] == (UNINC + "LENNOX", "geo_unincorporated")  # never becomes a city
    assert got["3670014A"] == (UNINC + "WEST ATHENS", "geo_unincorporated")
    assert got["9999999A"] == ("Los Angeles", "location")  # no shape: the place name is a city
    assert table["7000001A"]["contest_city"] == "Los Angeles"


def test_cross_checks_are_scored_against_the_shape(tmp_path):
    geo, boundary = inputs(tmp_path)
    _, diag = assign_all(list(parse(TEXT)), geo, boundary)
    assert (diag["contest_both"], diag["contest_agree"]) == (7, 6)  # 5 Carson + 6850002B agree; 7000001A does not
    assert diag["contest_pairs"][("Lomita", "Los Angeles")] == 1
    assert (diag["location_applies"], diag["location_correct"]) == (8, 8)  # 5 CARSON + 1030009B CARSON + 2 LOMITA
    assert diag["straddling"] == 0  # every shape is at least 90% inside its city


def test_precincts_that_straddle_a_city_line_are_counted(tmp_path):
    geo_csv = tmp_path / "g.csv"
    geo_csv.write_text("PRECINCT,city,overlap_share\n1030003A,Carson,1.0\n1030004A,Carson,0.62\n")
    _, boundary = inputs(tmp_path)
    blocks = list(parse(make_svc_text([(1, "COUNTY MEASURE G", [("CARSON", "1030003A", *ROW), ("CARSON", "1030004A", *ROW)])])))
    _, diag = assign_all(blocks, load_geo(geo_csv), boundary)
    assert diag["straddling"] == 1


def test_countywide_detection_and_aggregation(tmp_path):
    geo, boundary = inputs(tmp_path)
    blocks = list(parse(TEXT))
    table, _ = assign_all(blocks, geo, boundary)
    county = countywide_blocks(blocks)
    assert [b["title"] for b in county] == ["COUNTY MEASURE G"]
    agg = aggregate_by_city(county[0], table)
    assert agg["Carson"]["precincts"] == 7 and agg["Carson"]["ballots"] == 210 and agg["Carson"]["votes"] == [126, 84]
    assert agg["Carson"]["by_method"]["geo"] == 180 and agg["Carson"]["by_method"]["geo_base"] == 30
    assert agg["Lomita"]["precincts"] == 2 and agg["Los Angeles"]["precincts"] == 2
    assert agg["Los Angeles"]["by_method"]["location"] == 30
    assert agg[UNINC + "LENNOX"]["ballots"] == 30


def test_full_run_checks_sums_against_printed_totals(tmp_path):
    geo, gj = write_inputs(tmp_path)
    summary = run(TEXT, geo, gj, tmp_path / "out")
    assert summary["blocks"] == 3 and summary["blocks_with_errors"] == 0
    assert summary["precinct_methods"] == {"geo": 9, "geo_base": 1, "geo_unincorporated": 2, "location": 1}
    assert summary["contest_vs_geometry"]["agree"] == 6 and summary["contest_vs_geometry"]["precincts_compared"] == 7
    (only,) = summary["countywide_blocks"]
    assert only["match"] is True  # every group (cities and unincorporated places) adds up to the printed GRAND TOTAL
    rows = list(csv.DictReader(open(tmp_path / "out" / "countywide_by_city.csv")))
    assert {r["city"] for r in rows} == {"Carson", "Los Angeles", "Lomita", UNINC + "LENNOX", UNINC + "WEST ATHENS"}
    recon = {r["city"]: r for r in csv.DictReader(open(tmp_path / "out" / "city_reconciliation.csv"))}
    assert recon["Carson"]["reference_registration"] == "500" and recon["Carson"]["geometric_registration"] == "700"  # 2 shape-only precincts
    assert recon["Carson"]["difference_pct"] == "40.0"
    assert recon["Los Angeles"]["reference_registration"] == "200" and recon["Los Angeles"]["geometric_registration"] == "200"
    assert summary["reconciliation"]["cities"] == 2 and summary["reconciliation"]["within_1pct"] == 1
    assert recon["Carson"]["comparable"] == "True" and summary["reconciliation"]["district_only_not_comparable"] == []
    import gzip
    pv = list(csv.DictReader(gzip.open(tmp_path / "out" / "precinct_votes.csv.gz", "rt", newline="")))
    assert len(pv) == 13 and {r["seq"] for r in pv} == {str(only["seq"])} and pv[0]["ballots"] == "30" and pv[0]["choice_1"] == "18"   # 6 in person + 12 by mail
    for name in ("summary.md", "precinct_city.csv", "geo_vs_contest.csv", "city_reconciliation.csv"):
        assert (tmp_path / "out" / name).exists()


def test_a_corrupted_printed_total_is_caught(tmp_path):
    geo, gj = write_inputs(tmp_path)
    lines = TEXT.splitlines()
    start = next(k for k, l in enumerate(lines) if "COUNTY MEASURE G" in l)
    grand = next(k for k in range(start, len(lines)) if lines[k].startswith("GRAND TOTAL"))
    lines[grand] = lines[grand].rsplit("   ", 1)[0] + "   9999"  # printed total for the last choice is now wrong
    summary = run("\n".join(lines), geo, gj, tmp_path / "out2")
    assert summary["countywide_all_match"] is False


def test_a_city_with_only_district_contests_is_not_compared(tmp_path):
    geo, gj = write_inputs(tmp_path)
    text = make_svc_text([
        (1, "CARSON CITY GENERAL MUNICIPAL ELECTION Member of the City Council, 2nd District", [("CARSON", "1030003A", *ROW)]),
        (2, "COUNTY MEASURE G", [("CARSON", p, *ROW) for p in CARSON_LISTED])])
    summary = run(text, geo, gj, tmp_path / "out3")
    recon = {r["city"]: r for r in csv.DictReader(open(tmp_path / "out3" / "city_reconciliation.csv"))}
    assert recon["Carson"]["comparable"] == "False" and recon["Carson"]["difference_pct"] == "400.0"
    assert summary["reconciliation"]["comparable"] == 0 and summary["reconciliation"]["district_only_not_comparable"] == ["Carson"]
