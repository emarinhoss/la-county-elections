import pytest

from tools.arcgis_attrs import PAGE, download


def fake_layer(n):
    rows = [{"attributes": {"PRECINCT": f"{i:07d}A", "CITY_EST": f"{i:07d}", "SUBCODE": "A", "DST_CITY": "XX"}} for i in range(n)]

    def get(url):
        if "returnCountOnly=true" in url:
            return {"count": n}
        offset = int(url.split("resultOffset=")[1].split("&")[0])
        chunk = rows[offset:offset + PAGE]
        return {"features": chunk, "exceededTransferLimit": offset + PAGE < n}
    return get


def test_pages_until_all_rows_are_read():
    rows = download(fake_layer(PAGE * 2 + 5))
    assert len(rows) == PAGE * 2 + 5 and rows[-1]["PRECINCT"] == f"{PAGE * 2 + 4:07d}A"


def test_count_mismatch_is_an_error():
    good = fake_layer(10)

    def short(url):
        return {"count": 11} if "returnCountOnly=true" in url else good(url)
    with pytest.raises(SystemExit):
        download(short)
