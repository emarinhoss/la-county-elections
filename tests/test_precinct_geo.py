import json

import pytest

from tools.precinct_geo import PAGE, assign_cities, city_polygons, download_polygons


def box(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def feat(pid, geom):
    return {"type": "Feature", "properties": {"PRECINCT": pid}, "geometry": geom}


def cities(tmp_path):
    gj = tmp_path / "b.geojson"
    gj.write_text(json.dumps({"features": [
        {"properties": {"CITY_NAME": "Alpha", "CITY_TYPE": "City"}, "geometry": box(0, 0, 10, 10)},
        {"properties": {"CITY_NAME": "Beta", "CITY_TYPE": "City"}, "geometry": box(10, 0, 20, 10)},
        {"properties": {"CITY_NAME": "Beta", "CITY_TYPE": "City"}, "geometry": box(10, 10, 20, 20)},  # a second piece of Beta
        {"properties": {"CITY_NAME": "Unincorporated", "CITY_TYPE": "Unincorporated"}, "geometry": box(20, 0, 40, 10)}]}))
    return city_polygons(gj)


def assign_one(c, pid, geom):
    ((_, city, share),) = assign_cities([feat(pid, geom)], c)
    return city, share


def test_precinct_goes_to_the_city_that_covers_most_of_it(tmp_path):
    c = cities(tmp_path)
    assert set(c) == {"Alpha", "Beta"}  # the unincorporated polygon is not a city
    assert assign_one(c, "inA", box(1, 1, 3, 3)) == ("Alpha", 1.0)
    assert assign_one(c, "second piece of Beta", box(12, 12, 14, 14)) == ("Beta", 1.0)
    city, share = assign_one(c, "straddles", box(3, 1, 13, 3))  # x 3..13: 7 wide in Alpha, 3 wide in Beta
    assert city == "Alpha" and share == pytest.approx(0.7)


def test_precinct_outside_every_city_is_unincorporated(tmp_path):
    c = cities(tmp_path)
    assert assign_one(c, "in the unincorporated polygon", box(25, 1, 27, 3)) == ("", 0.0)


def test_a_precinct_needs_at_least_half_of_itself_inside_a_city(tmp_path):
    c = cities(tmp_path)
    # x 8..28 is 20 wide: 2 in Alpha, 10 in Beta, 8 outside -> Beta covers exactly half: assigned
    assert assign_one(c, "half", box(8, 1, 28, 3)) == ("Beta", 0.5)
    # x 9.5..32 is 22.5 wide: 0.5 in Alpha, 10 in Beta, 12 outside -> Beta covers 44%: unincorporated
    assert assign_one(c, "under half", box(9.5, 1, 32, 3)) == ("", 0.0)


def fake_layer(n):
    feats = [feat(f"{i:07d}A", box(i, 0, i + 1, 1)) for i in range(n)]

    def get(url):
        if "returnCountOnly=true" in url:
            return {"count": n}
        offset = int(url.split("resultOffset=")[1].split("&")[0])
        return {"type": "FeatureCollection", "features": feats[offset:offset + PAGE]}
    return get


def test_download_pages_and_checks_the_count():
    assert len(download_polygons(fake_layer(PAGE * 2 + 3))) == PAGE * 2 + 3
    good = fake_layer(5)

    def short(url):
        return {"count": 6} if "returnCountOnly=true" in url else good(url)
    with pytest.raises(SystemExit):
        download_polygons(short)
