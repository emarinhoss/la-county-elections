import csv
import json

from tools.svc_pipeline import (UNASSIGNED, aggregate_by_city, assign_all, city_from_title, countywide_blocks,
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


ROW = ([10, 6, 4], [20, 12, 8], 100)  # in-person, vote-by-mail, registration: every precinct has the same numbers
CARSON_DIRECT = [f"103000{i}A" for i in range(3, 8)]  # 5 precincts listed in Carson's own contest
ALL = [("CARSON", p, *ROW) for p in CARSON_DIRECT] + [
    ("WEST CARSON", "1030008A", *ROW),   # code CC, but not in any city contest, and the location is not a city
    ("SUNLAND", "6850002B", *ROW),       # inside the Los Angeles measure
    ("LOMITA", "7000001A", *ROW),        # code LM, inside the Los Angeles measure (a Los Angeles precinct with a Lomita place name)
    ("LOMITA", "7000002A", *ROW),        # code LM, in no city contest: really Lomita
    ("LENNOX", "3670013A", *ROW),        # unincorporated, code ZZ
    ("WEST ATHENS", "3670014A", *ROW),   # unincorporated, code ZZ
    ("LOS ANGELES", "9999999A", *ROW),   # not in the precinct layer at all
]
BLOCKS = [
    (1, "CARSON CITY GENERAL MUNICIPAL ELECTION Mayor", [("CARSON", p, *ROW) for p in CARSON_DIRECT]),
    (2, "COUNTY MEASURE G", ALL),
    (3, "LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE LL", [("SUNLAND", "6850002B", *ROW), ("LOMITA", "7000001A", *ROW)]),
]
TEXT = make_svc_text(BLOCKS)
LAYER_ROWS = ([(p, p[:7], "A", "CC") for p in CARSON_DIRECT + ["1030008A"]] + [("6850002B", "6850002", "B", "LA"),
              ("7000001A", "7000001", "A", "LM"), ("7000002A", "7000002", "A", "LM"),
              ("3670013A", "3670013", "A", "ZZ"), ("3670014A", "3670014", "A", "ZZ")])


def write_inputs(tmp_path):
    layer = tmp_path / "layer.csv"
    with open(layer, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["PRECINCT", "CITY_EST", "SUBCODE", "DST_CITY"])
        w.writerows(LAYER_ROWS)
    gj = tmp_path / "b.geojson"
    gj.write_text(json.dumps({"features": [{"properties": {"CITY_NAME": n, "CITY_TYPE": t}} for n, t in
                                           [("Carson", "City"), ("Los Angeles", "City"), ("Lomita", "City"),
                                            ("Culver City", "City"), ("Unincorporated", "Unincorporated")]]}))
    return layer, gj


def inputs(tmp_path):
    layer, gj = write_inputs(tmp_path)
    return load_layer(layer), load_boundary_cities(gj)


def test_generated_text_is_valid_for_the_parser():
    from tools.svc_parse import check_block
    for b in parse(TEXT):
        assert check_block(b) == ([], [])


def test_map_precinct_exact_base_and_none(tmp_path):
    layer, _ = inputs(tmp_path)
    assert map_precinct("1030003A", layer) == ("CC", "exact")
    assert map_precinct("1030003Z", layer) == ("CC", "base")  # unknown suffix, known 7-digit base
    assert map_precinct("9999999A", layer) == (None, "unmatched")


def test_city_from_title_handles_both_styles(tmp_path):
    _, boundary = inputs(tmp_path)
    assert city_from_title("CARSON CITY GENERAL MUNICIPAL ELECTION Mayor", boundary) == "Carson"
    assert city_from_title("LOS ANGELES CITY GENERAL MUNICIPAL ELECTION - MEASURE LL", boundary) == "Los Angeles"
    assert city_from_title("CITY OF CULVER CITY GENERAL MUNICIPAL ELECTION Mayor", boundary) == "Culver City"
    assert city_from_title("COUNTY MEASURE G", boundary) is None
    assert city_from_title("CITY OF NOWHERE GENERAL MUNICIPAL ELECTION Mayor", boundary) is None


def test_each_precinct_is_assigned_by_the_strongest_evidence(tmp_path):
    layer, boundary = inputs(tmp_path)
    table, diag = assign_all(list(parse(TEXT)), layer, boundary)
    got = {pid: (t["city"], t["method"]) for pid, t in table.items()}
    assert got["1030003A"] == ("Carson", "direct")
    assert got["1030008A"] == ("Carson", "code")  # pure code CC beats the non-city place name WEST CARSON
    assert got["6850002B"] == ("Los Angeles", "direct")
    assert got["7000001A"] == ("Los Angeles", "direct")  # direct evidence beats its LOMITA place name and mixed code LM
    assert got["7000002A"] == ("Lomita", "location")  # code LM is not pure, so only the place name is left
    assert got["3670013A"] == (UNASSIGNED + "LENNOX", "unassigned")  # ZZ never becomes a city
    assert got["3670014A"] == (UNASSIGNED + "WEST ATHENS", "unassigned")
    assert got["9999999A"] == ("Los Angeles", "location")  # not in the layer: place name is a city
    assert diag["purity"]["CC"]["pure"] is True and diag["purity"]["LM"]["pure"] is False
    assert diag["direct_precincts"] == 7 and diag["conflicts"] == {}


def test_fallback_rules_are_scored_on_known_answers(tmp_path):
    layer, boundary = inputs(tmp_path)
    _, diag = assign_all(list(parse(TEXT)), layer, boundary)
    sc = diag["fallback_score"]
    assert (sc["code_applies"], sc["code_correct"]) == (5, 5)  # CC evidence stays pure with any one Carson precinct left out
    assert (sc["location_applies"], sc["location_correct"]) == (6, 5)  # 7000001A says LOMITA but is a Los Angeles precinct


def test_countywide_detection_and_aggregation(tmp_path):
    layer, boundary = inputs(tmp_path)
    blocks = list(parse(TEXT))
    table, _ = assign_all(blocks, layer, boundary)
    county = countywide_blocks(blocks)
    assert [b["title"] for b in county] == ["COUNTY MEASURE G"]
    agg = aggregate_by_city(county[0], table)
    assert agg["Carson"]["precincts"] == 6 and agg["Carson"]["ballots"] == 180 and agg["Carson"]["votes"] == [108, 72]
    assert agg["Carson"]["by_method"]["direct"] == 150 and agg["Carson"]["by_method"]["code"] == 30
    assert agg["Los Angeles"]["precincts"] == 3 and agg["Los Angeles"]["by_method"]["location"] == 30
    assert agg["Lomita"]["precincts"] == 1
    assert agg[UNASSIGNED + "LENNOX"]["ballots"] == 30


def test_full_run_checks_sums_against_printed_totals(tmp_path):
    layer, gj = write_inputs(tmp_path)
    summary = run(TEXT, layer, gj, tmp_path / "out")
    assert summary["blocks"] == 3 and summary["blocks_with_errors"] == 0
    assert summary["precinct_methods"] == {"direct": 7, "code": 1, "location": 2, "unassigned": 2}
    assert summary["precincts_not_in_layer"] == 1 and summary["codes_pure"] == ["CC"] and summary["codes_mixed"] == []
    (only,) = summary["countywide_blocks"]
    assert only["match"] is True  # every group (cities and unassigned places) adds up to the printed GRAND TOTAL
    rows = list(csv.DictReader(open(tmp_path / "out" / "countywide_by_city.csv")))
    assert {r["city"] for r in rows} == {"Carson", "Los Angeles", "Lomita", UNASSIGNED + "LENNOX", UNASSIGNED + "WEST ATHENS"}
    for name in ("summary.md", "precinct_city.csv", "code_purity.csv"):
        assert (tmp_path / "out" / name).exists()


def test_a_corrupted_printed_total_is_caught(tmp_path):
    layer, gj = write_inputs(tmp_path)
    lines = TEXT.splitlines()
    start = next(k for k, l in enumerate(lines) if "COUNTY MEASURE G" in l)
    grand = next(k for k in range(start, len(lines)) if lines[k].startswith("GRAND TOTAL"))
    lines[grand] = lines[grand].rsplit("   ", 1)[0] + "   9999"  # printed total for the last choice is now wrong
    summary = run("\n".join(lines), layer, gj, tmp_path / "out2")
    assert summary["countywide_all_match"] is False
