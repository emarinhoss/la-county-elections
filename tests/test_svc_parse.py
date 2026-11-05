from pathlib import Path

from tools.svc_parse import by_location, check_block, normalize_title, parse

FIX26 = Path(__file__).parent / "fixtures" / "svc2026"

FIX = Path(__file__).parent / "fixtures" / "svc"


def blocks(name):
    return list(parse((FIX / name).read_text()))


def test_carson_mayor_is_parsed_and_matches_its_printed_totals():
    (b,) = blocks("carson_mayor_pages_1_3.txt")
    assert b["seq"] == 1 and b["title"] == "CARSON CITY GENERAL MUNICIPAL ELECTION Mayor"
    assert len(b["precincts"]) > 20
    first = b["precincts"][0]
    assert (first["location"], first["precinct"], first["star"]) == ("CARSON", "1030003A", False)
    assert first["in_person"] == [487, 217, 246] and first["vbm"] == [1084, 359, 675]
    assert first["registration"] == 2750 and first["total"] == [1571, 576, 921]
    assert b["precincts"][2]["star"] is True  # "1030010A*"
    assert b["totals"]["GRAND TOTAL"] == [63517, 39707, 14998, 22749]
    errors, notes = check_block(b)
    assert errors == []  # every row adds up, and every vote column adds up to the printed totals
    # The county's own printed totals are 1 voter / 1 ballot above its precinct rows (votes match exactly).
    assert len(notes) == 2 and "VBM TOTAL" in notes[0] and "GRAND TOTAL" in notes[1]


def test_check_catches_a_wrong_number():
    (b,) = blocks("carson_mayor_pages_1_3.txt")
    b["precincts"][0]["total"][1] += 1
    errors, _ = check_block(b)
    assert any("in-person + mail" in p for p in errors) and any("vote columns" in p for p in errors)


def test_page_without_the_end_of_the_contest_is_flagged_not_trusted():
    (b,) = blocks("state_senate_35_page.txt")
    assert b["title"] == "Voter Nominated : STATE SENATOR, 35th District"
    assert normalize_title(b["title"]) == "STATE SENATOR, 35TH DISTRICT"
    assert {r["location"] for r in b["precincts"]} >= {"LENNOX", "WEST ATHENS"}
    assert any("may continue" in p for p in check_block(b)[0])


def test_countywide_measure_page_parses_two_choices():
    (b,) = blocks("county_measure_g_page.txt")
    assert b["title"] == "COUNTY MEASURE G" and all(len(r["total"]) == 3 for r in b["precincts"])
    assert b["precincts"][0]["location"] == "LOS ANGELES"


def test_contest_ends_on_last_page_and_two_candidate_senate_totals():
    (b,) = blocks("us_senate_pages_end.txt")
    assert b["seq"] == 373 and "UNITED STATES SENATOR" in normalize_title(b["title"])
    assert b["totals"]["PRECINCT TOTAL"] == [1060354, 469039, 518847]
    assert b["totals"]["VBM TOTAL"] == [2742791, 764677, 1804741]


def test_by_location_sums_precincts():
    (b,) = blocks("carson_mayor_pages_1_3.txt")
    carson = by_location(b)["CARSON"]
    assert carson["ballots"] == sum(r["total"][0] for r in b["precincts"])
    assert carson["votes"] == [sum(r["total"][1 + i] for r in b["precincts"]) for i in range(2)]


def blocks26(name):
    return list(parse((FIX26 / name).read_text()))


def test_2026_plain_title_and_status_label():
    (b,) = blocks26("compton_mayor_page1.txt")
    assert b["title"] == "CITY OF COMPTON GENERAL MUNICIPAL ELECTION Mayor"
    assert b["status"] == "SEMIFINAL OFFICIAL CANVASS V2"
    assert b["header"].startswith("CITY OF COMPTON GENERAL MUNICIPAL ELECTION Mayor") and "EMMA SHARIF" in b["header"]
    assert b["precincts"][0]["location"] == "COMPTON" and b["precincts"][0]["precinct"] == "1450006A" and b["precincts"][0]["star"] is True


def test_2026_voter_nominated_title_is_on_the_next_line_and_stays_in_the_header():
    (b,) = blocks26("voter_nominated_boe_page.txt")
    assert b["title"] == "Voter Nominated :"  # the first line alone is not the title...
    assert "MEMBER STATE BOARD OF EQUALIZATION 3rd District" in b["header"]  # ...but the whole header holds it
    assert b["header"].index("Voter Nominated :") < b["header"].index("MEMBER STATE BOARD")
    assert b["status"] == "SEMIFINAL OFFICIAL CANVASS V2"


def test_2026_results_only_prefix_and_retention_question_are_in_the_header():
    (m,) = blocks26("results_only_state_measure_39_page.txt")
    assert "Los Angeles County Results Only" in m["header"] and "STATE MEASURE 39" in m["header"]
    (r,) = blocks26("retention_presiding_justice_page.txt")
    assert "For Presiding Justice, Court of Appeal, Second District, Division Three Shall Presiding Justice RASHIDA A. ADAMS be elected" in r["header"]
    assert "to the office for the term provided by law?" in r["header"] and "Results Only" in r["header"]
    assert r["precincts"] and len(r["precincts"][0]["total"]) == 3  # ballots cast, YES, NO


def test_the_header_is_read_from_the_first_page_of_a_contest_only():
    text = (FIX26 / "compton_mayor_page1.txt").read_text()
    second_page = text.replace("1.1   -Page- 1", "1.2   -Page- 2")  # same contest number, next page: header must not be added again
    (b,) = list(parse(text + "\n" + second_page))
    assert b["header"].count("EMMA SHARIF") == 1 and len(b["precincts"]) == 2 * len(blocks26("compton_mayor_page1.txt")[0]["precincts"])
