import csv
import json

from tools.svc_pipeline import (UNMATCHED, aggregate_by_city, build_code_table, city_from_title, countywide_blocks,
                                load_boundary_cities, load_layer, map_precinct, run)
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


BLOCKS = [
    (1, "CARSON CITY GENERAL MUNICIPAL ELECTION Mayor", [
        ("CARSON", "1030003A", [10, 6, 4], [20, 12, 8], 100), ("CARSON", "1030004A", [5, 2, 3], [15, 9, 6], 80)]),
    (2, "COUNTY MEASURE G", [
        ("CARSON", "1030003A", [10, 6, 4], [20, 12, 8], 100), ("CARSON", "1030004A", [5, 2, 3], [15, 9, 6], 80),
        ("SUNLAND", "6850002B", [7, 4, 3], [9, 5, 4], 60), ("LENNOX", "3670013A", [8, 5, 3], [12, 6, 6], 70),
        ("LOS ANGELES", "9999999A", [3, 1, 2], [4, 3, 1], 20)]),
    (3, "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE LL", [
        ("SUNLAND", "6850002B", [7, 4, 3], [9, 5, 4], 60)]),
]
TEXT = make_svc_text(BLOCKS)
LAYER_ROWS = [("1030003A", "1030003", "A", "CC"), ("1030004A", "1030004", "A", "CC"), ("6850002B", "6850002", "B", "LA"), ("3670013A", "3670013", "A", "UN")]


def write_inputs(tmp_path):
    layer = tmp_path / "layer.csv"
    with open(layer, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["PRECINCT", "CITY_EST", "SUBCODE", "DST_CITY"])
        w.writerows(LAYER_ROWS)
    gj = tmp_path / "b.geojson"
    gj.write_text(json.dumps({"features": [{"properties": {"CITY_NAME": n, "CITY_TYPE": t}} for n, t in
                                           [("Carson", "City"), ("Los Angeles", "City"), ("Culver City", "City"), ("Unincorporated", "Unincorporated")]]}))
    return layer, gj


def test_generated_text_is_valid_for_the_parser():
    for b in parse(TEXT):
        assert check_ok(b)


def check_ok(b):
    from tools.svc_parse import check_block
    return check_block(b) == ([], [])


def test_map_precinct_exact_base_and_none(tmp_path):
    layer = load_layer(write_inputs(tmp_path)[0])
    assert map_precinct("1030003A", layer) == ("CC", "exact")
    assert map_precinct("1030003Z", layer) == ("CC", "base")  # unknown suffix, known 7-digit base
    assert map_precinct("9999999A", layer) == (None, "unmatched")


def test_city_from_title_handles_both_styles(tmp_path):
    boundary = load_boundary_cities(write_inputs(tmp_path)[1])
    assert city_from_title("CARSON CITY GENERAL MUNICIPAL ELECTION Mayor", boundary) == "Carson"
    assert city_from_title("LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE LL", boundary) == "Los Angeles"
    assert city_from_title("CITY OF CULVER CITY GENERAL MUNICIPAL ELECTION Mayor", boundary) == "Culver City"
    assert city_from_title("COUNTY MEASURE G", boundary) is None
    assert city_from_title("CITY OF NOWHERE GENERAL MUNICIPAL ELECTION Mayor", boundary) is None


def test_codes_are_named_from_city_contests_not_from_location_text(tmp_path):
    layer, gj = load_layer(write_inputs(tmp_path)[0]), load_boundary_cities(write_inputs(tmp_path)[1])
    table = build_code_table(list(parse(TEXT)), layer, gj)
    assert table["CC"]["city"] == "Carson" and table["CC"]["method"] == "city_contest"
    assert table["LA"]["city"] == "Los Angeles"  # precinct location text says SUNLAND, the contest says Los Angeles
    assert table["UN"]["city"] is None and table["UN"]["method"] == "unnamed"  # LENNOX is not a city: left unnamed, not guessed


def test_countywide_detection_and_aggregation(tmp_path):
    inputs = write_inputs(tmp_path)
    layer, boundary = load_layer(inputs[0]), load_boundary_cities(inputs[1])
    blocks = list(parse(TEXT))
    table = build_code_table(blocks, layer, boundary)
    county = countywide_blocks(blocks)
    assert [b["title"] for b in county] == ["COUNTY MEASURE G"]
    agg = aggregate_by_city(county[0], layer, table)
    assert agg["Carson"]["ballots"] == 30 + 20 and agg["Carson"]["votes"] == [18 + 11, 12 + 9]
    assert agg["Los Angeles"]["votes"] == [9, 7]
    assert agg["UNNAMED:UN"]["ballots"] == 20
    assert agg[UNMATCHED]["ballots"] == 7


def test_full_run_checks_sums_against_printed_totals_and_reports_unnamed(tmp_path):
    layer, gj = write_inputs(tmp_path)
    summary = run(TEXT, layer, gj, tmp_path / "out")
    assert summary["blocks"] == 3 and summary["blocks_with_errors"] == 0
    assert summary["match_exact"] == 7 and summary["match_none"] == 1  # 8 precinct rows; 9999999A has no layer row
    assert summary["codes_unnamed"] == ["UN"]
    (only,) = summary["countywide_blocks"]
    assert only["match"] is True  # votes by city (incl. unnamed and unmatched groups) equal the printed GRAND TOTAL
    rows = list(csv.DictReader(open(tmp_path / "out" / "countywide_by_city.csv")))
    assert {r["city"] for r in rows} == {"Carson", "Los Angeles", "UNNAMED:UN", UNMATCHED}
    assert (tmp_path / "out" / "summary.md").exists()


def test_a_corrupted_printed_total_is_caught(tmp_path):
    layer, gj = write_inputs(tmp_path)
    lines = TEXT.splitlines()
    start = next(k for k, l in enumerate(lines) if "COUNTY MEASURE G" in l)
    grand = next(k for k in range(start, len(lines)) if lines[k].startswith("GRAND TOTAL"))
    lines[grand] = lines[grand].rsplit("   ", 1)[0] + "   9999"  # printed total for the last choice is now wrong
    summary = run("\n".join(lines), layer, gj, tmp_path / "out2")
    assert summary["countywide_all_match"] is False
