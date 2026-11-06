from sitegen.measure_title import measure_title as mt


def test_headline_before_type_labels():
    assert mt("AUTHORIZES BONDS FOR HOUSING AFFORDABILITY PROGRAMS. LEGISLATIVE STATUTE. Authorizes $11.25 billion in bonds.") == "Authorizes Bonds for Housing Affordability Programs"
    assert mt("CITY ETHICS, ELECTIONS, AND GOVERNANCE. CHARTER AMENDMENT EE. Shall the City Charter be amended to: x") == "City Ethics, Elections, and Governance"
    assert mt("PROPOSED COUNTY CHARTER AMENDMENT. COUNTY OF LOS ANGELES ETHICS COMMISSION CHARTER AMENDMENT. Shall the measure") == "County of Los Angeles Ethics Commission Charter Amendment"


def test_caps_headline_running_into_the_question_and_hyphens_and_slashes():
    assert mt("LOS ANGELES COUNTY CHARTER AMENDMENT ON NEGOTIATION Shall the measure amending the Charter") == "Los Angeles County Charter Amendment on Negotiation"
    assert mt("CREATES LOAN PROGRAM FOR MIDDLE-INCOME BUYERS. INITIATIVE STATUTE. Authorizes $25 billion") == "Creates Loan Program for Middle-Income Buyers"
    assert mt("SOUTH PASADENA STREET/ROAD/POTHOLE REPAIR, 9-1-1 SAFETY MEASURE. To fix streets") == "South Pasadena Street/Road/Pothole Repair, 9-1-1 Safety Measure"


def test_measure_prefix_and_mixed_case_headlines():
    assert mt("MEASURE ES: Shall a measure imposing a parcel tax of $495 be adopted?") == "Shall a measure imposing a parcel tax of $495 be adopted?"
    assert mt("Data Centers Prohibited. Shall an ordinance be adopted affirming the ban?") == "Data Centers Prohibited"
    assert mt("Good Government Cannabis Reform Measure To fund general city services in Baldwin Park, such as streets") == "Good Government Cannabis Reform Measure"
    assert mt("CITY OF BURBANK CITY SERVICES MEASURE: MEASURE C: To maintain services including fire") == "City of Burbank City Services"


def test_plain_question_is_used_verbatim_and_long_ones_are_cut():
    q = "Shall the measure permitting the City of Bell Gardens to sell its water system be adopted? Yes No"
    assert mt(q) == "Shall the measure permitting the City of Bell Gardens to sell its water system be adopted?"
    long = "Shall the City Charter be amended to " + "prohibit evictions " * 30 + "by the U.S. Department of Housing."
    out = mt(long)
    assert out.endswith("...") and len(out) <= 194 and "U.S" in long
    assert mt("U.S. thing. Shall x?") is not None


def test_caps_emphasis_is_not_a_headline_and_no_text_gives_none():
    out = mt("WITHOUT INCREASING EXISTING TAX RATES, to upgrade safety systems; repair classrooms")
    assert out == "Without increasing existing tax rates, to upgrade safety systems; repair classrooms"
    assert mt("") is None and mt(None) is None
