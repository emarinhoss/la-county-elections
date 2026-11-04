import pytest

from sitegen.boundaries import join

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}


def feat(name, kind="City"):
    return {"type": "Feature", "geometry": SQUARE, "properties": {"CITY_NAME": name, "CITY_TYPE": kind}}


def test_join_matches_by_key_and_reports_missing():
    gj = {"features": [feat("La Cañada Flintridge"), feat("Alhambra"), feat("Altadena", "Unincorporated")]}
    out, report = join(gj, {"lacanadaflintridge", "alhambra", "ghosttown"})
    flags = {f["properties"]["name"]: f["properties"]["has_contests"] for f in out["features"]}
    assert flags == {"La Cañada Flintridge": True, "Alhambra": True, "Altadena": False}
    assert report["cities_with_contests_but_no_polygon"] == ["ghosttown"]
    assert out["features"][2]["properties"]["kind"] == "unincorporated"


def test_unknown_field_names_stop_with_a_clear_message():
    gj = {"features": [{"type": "Feature", "geometry": SQUARE, "properties": {"WEIRD": "x"}}]}
    with pytest.raises(SystemExit) as e:
        join(gj, {"a"})
    assert "WEIRD" in str(e.value)
