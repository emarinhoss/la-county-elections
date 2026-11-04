"""Take a small, committable sample from a big Statement of Votes Cast (SVC) PDF.

The full PDFs are tens of MB, too big to commit. This keeps: the PDF's metadata (pdfinfo), its size and
sha256, and the layout-preserving text of a handful of pages, so we can see the real layout and write a
parser against it. Needs poppler (pdftotext, pdfinfo).

Usage: python -m tools.svc_sample <pdf> <out_dir> <source_url>
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ALLOWED_PREFIX = "https://content.lavote.gov/docs/rrcc/svc/"
MAX_PAGE_CHARS = 200_000  # one page of an SVC is a few KB; this only stops a runaway


def check_url(url):
    """Only county SVC files may be sampled. Stops a typo or a bad input from fetching anything else."""
    if not (url.startswith(ALLOWED_PREFIX) and url.endswith(".pdf")) or re.search(r"[\s'\"`$;|&<>]", url):
        raise SystemExit(f"refusing url {url!r}: must be {ALLOWED_PREFIX}*.pdf")


def pick_pages(n_pages, n_middle=6):
    """First 3 pages, evenly spaced pages through the middle, and the last 2. 1-based, sorted, unique."""
    if n_pages <= 12:
        return list(range(1, n_pages + 1))
    middle = [round(n_pages * k / (n_middle + 1)) for k in range(1, n_middle + 1)]
    return sorted({1, 2, 3, *middle, n_pages - 1, n_pages})


def page_count(pdfinfo_text):
    m = re.search(r"^Pages:\s+(\d+)", pdfinfo_text, re.M)
    if not m:
        raise SystemExit("pdfinfo output has no Pages line")
    return int(m.group(1))


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def sample(pdf, out_dir, url):
    pdf, out = Path(pdf), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    info = run(["pdfinfo", str(pdf)])
    n = page_count(info)
    pages = pick_pages(n)
    chars = {}
    for p in pages:
        text = run(["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf), "-"])[:MAX_PAGE_CHARS]
        (out / f"page_{p:05d}.txt").write_text(text)
        chars[p] = len(text.strip())
    manifest = {
        "source_url": url, "bytes": pdf.stat().st_size, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "pages": n, "sampled_pages": pages, "non_blank_chars_per_sampled_page": chars,
        "text_extraction": "pdftotext -layout (poppler)",
    }
    (out / "pdfinfo.txt").write_text(info)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    pdf, out_dir, url = sys.argv[1:4]
    check_url(url)
    m = sample(pdf, out_dir, url)
    print(f"{m['pages']} pages, {m['bytes']} bytes, sampled {len(m['sampled_pages'])} pages: {m['sampled_pages']}")
    blank = [p for p, c in m["non_blank_chars_per_sampled_page"].items() if c == 0]
    if blank:
        print("WARNING: no text on pages", blank, "- the PDF may be scanned images")
