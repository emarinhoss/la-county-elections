import json
import shutil

import pytest

from tools.svc_sample import ALLOWED_PREFIX, check_url, page_count, pick_pages, sample


def make_pdf(path, n_pages):
    """Smallest valid PDF with one line of text per page (built by hand so the test needs no PDF library)."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [" + " ".join(f"{3 + i} 0 R" for i in range(n_pages)) + f"] /Count {n_pages} >>"]
    font = 3 + 2 * n_pages
    for i in range(n_pages):
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents {3 + n_pages + i} 0 R "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> >>")
    for i in range(n_pages):
        stream = f"BT /F1 12 Tf 10 50 Td (PRECINCT 000{i + 1} BECERRA 123) Tj ET"
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{off:010d} 00000 n \n" for off in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


def test_pick_pages():
    assert pick_pages(5) == [1, 2, 3, 4, 5]
    p = pick_pages(4000)
    assert p[:3] == [1, 2, 3] and p[-2:] == [3999, 4000] and len(p) == len(set(p)) and p == sorted(p)
    assert len(p) <= 11


def test_page_count_parses_pdfinfo():
    assert page_count("Title: x\nPages:          1234\nPage size: 612 x 792 pts") == 1234
    with pytest.raises(SystemExit):
        page_count("no pages here")


def test_only_county_svc_pdfs_are_allowed():
    check_url(ALLOWED_PREFIX + "4324_final_svc_precinct_public.pdf")
    for bad in ["https://example.com/x.pdf", ALLOWED_PREFIX + "x.zip", ALLOWED_PREFIX + "x.pdf; rm -rf /",
                ALLOWED_PREFIX + "a b.pdf", "file:///etc/passwd"]:
        with pytest.raises(SystemExit):
            check_url(bad)


@pytest.mark.skipif(shutil.which("pdfinfo") is None, reason="needs poppler-utils (pdfinfo, pdftotext)")
def test_sample_writes_pages_and_manifest(tmp_path):
    pdf = tmp_path / "t.pdf"
    make_pdf(pdf, 4)
    m = sample(pdf, tmp_path / "out", ALLOWED_PREFIX + "t.pdf")
    assert m["pages"] == 4 and m["sampled_pages"] == [1, 2, 3, 4]
    assert "PRECINCT 0003 BECERRA 123" in (tmp_path / "out" / "page_00003.txt").read_text()
    assert json.loads((tmp_path / "out" / "manifest.json").read_text())["sha256"] == m["sha256"]
    assert (tmp_path / "out" / "pdfinfo.txt").exists()
