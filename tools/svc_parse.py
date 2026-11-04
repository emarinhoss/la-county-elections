"""Parse the text of a county Statement of Votes Cast "by precinct" PDF (from `pdftotext -layout`).

Layout seen in the 2024 general election file (read from real sample pages):
  - every page starts with:  COUNTY OF LOS ANGELES  <date>  <election>   <contest#>.<page#>   -Page- <n>
  - the first non-blank line after that is the contest title (maybe prefixed "Voter Nominated :")
  - each precinct is three rows:
        <LOCATION> - <PRECINCT>[*]      ballots  vote1 vote2 ...       (in-person)
         VOTE BY MAIL   SERIAL nnnn     ballots  vote1 vote2 ...
        TOTAL                           registration  ballots  vote1 vote2 ...
  - a contest ends with PRECINCT TOTAL, VBM TOTAL and GRAND TOTAL rows, which we use to check our own parsing.
Candidate names are wrapped over several header lines, so we do NOT read them. Vote columns are kept in
order and matched to the county API's choice order later (and checked against its totals).

The LOCATION text is a community name (CARSON, SUNLAND, WEST ATHENS...), not always a city.
"""
import re
from collections import defaultdict

PAGE = re.compile(r"^COUNTY OF LOS ANGELES\s+.*?(\d+)\.(\d+)\s+-Page-\s+(\d+)\s*$")
NUMS = r"(?P<nums>(?:\d[\d,]*\s*)*)"
PRECINCT_ROW = re.compile(r"^(?P<loc>[A-Z0-9][A-Z0-9 .&'/()-]*?) - (?P<pid>\d{6,8}[A-Z]?)(?P<star>\*?)\s*" + NUMS + r"$")
VBM_ROW = re.compile(r"^\s*VOTE BY MAIL\s+SERIAL\s+(?P<serial>\d+)\s*" + NUMS + r"$")
TOTAL_ROW = re.compile(r"^TOTAL\s+" + NUMS + r"$")
SUM_ROW = re.compile(r"^(?P<kind>PRECINCT TOTAL|VBM TOTAL|GRAND TOTAL)\s+" + NUMS + r"$")


def ints(text):
    return [int(x.replace(",", "")) for x in text.split()]


def normalize_title(title):
    """Make a PDF contest title comparable with the API title (case, spaces, 'Voter Nominated :' prefix)."""
    t = re.sub(r"^\s*Voter Nominated\s*:\s*", "", title.strip(), flags=re.I)
    return re.sub(r"\s+", " ", t).upper()


def parse(text):
    """Yield one dict per contest block: seq, title, precincts, totals."""
    block, pending, want_title = None, None, False
    for raw in text.splitlines():
        line = raw.rstrip().replace("\f", "")
        m = PAGE.match(line)
        if m:
            seq = int(m.group(1))
            if block is None or seq != block["seq"]:
                if block:
                    yield block
                block = {"seq": seq, "title": None, "precincts": [], "totals": {}}
                pending = None
            want_title = block["title"] is None
            continue
        if block is None or not line.strip():
            continue
        if want_title:
            block["title"] = re.sub(r"\s+", " ", line.strip())
            want_title = False
            continue
        m = SUM_ROW.match(line)
        if m:
            block["totals"][m.group("kind")] = ints(m.group("nums"))
            continue
        m = PRECINCT_ROW.match(line)
        if m:
            pending = {"location": m.group("loc").strip(), "precinct": m.group("pid"), "star": bool(m.group("star")),
                       "in_person": ints(m.group("nums")), "vbm": None}
            continue
        m = VBM_ROW.match(line)
        if m and pending:
            pending["vbm"] = ints(m.group("nums"))
            continue
        m = TOTAL_ROW.match(line)
        if m and pending and pending["vbm"] is not None:
            nums = ints(m.group("nums"))
            pending.update(registration=nums[0], total=nums[1:])
            block["precincts"].append(pending)
            pending = None
    if block:
        yield block


def check_block(block):
    """Compare our parse with the PDF's own printed totals. Returns (errors, notes).

    errors: a row that does not add up, or vote columns that differ from the printed totals. Do not trust the block.
    notes:  registration or ballots-cast totals that differ from the precinct rows. In the real 2024 file the Carson
            mayor block is 1 voter / 1 ballot higher than its precinct rows while every vote column matches
            exactly, so these are reported, not treated as parse failures.
    """
    errors, notes, rows, t = [], [], block["precincts"], block["totals"]
    for r in rows:
        if len(r["in_person"]) != len(r["vbm"]) or len(r["total"]) != len(r["vbm"]):
            errors.append(f"{r['location']} {r['precinct']}: column counts differ")
        elif [a + b for a, b in zip(r["in_person"], r["vbm"])] != r["total"]:
            errors.append(f"{r['location']} {r['precinct']}: in-person + mail != total")
    if not rows:
        return errors, notes
    if not {"PRECINCT TOTAL", "VBM TOTAL", "GRAND TOTAL"} <= set(t):
        errors.append("no PRECINCT/VBM/GRAND TOTAL rows (block may continue on pages we do not have)")
        return errors, notes
    width = len(t["PRECINCT TOTAL"])  # ballots cast + one column per choice
    ok = [r for r in rows if len(r["total"]) == width]
    sums = {
        "PRECINCT TOTAL": [sum(r["in_person"][i] for r in ok) for i in range(width)],
        "VBM TOTAL": [sum(r["vbm"][i] for r in ok) for i in range(width)],
        "GRAND TOTAL": [sum(r["registration"] for r in ok)] + [sum(r["total"][i] for r in ok) for i in range(width)],
    }
    for name, got in sums.items():
        printed = t[name]
        if len(printed) != len(got):
            errors.append(f"{name}: {len(printed)} printed columns, expected {len(got)}")
            continue
        first_votes = 2 if name == "GRAND TOTAL" else 1  # skip registration/ballots columns
        if got[first_votes:] != printed[first_votes:]:
            errors.append(f"{name}: vote columns parsed {got[first_votes:]} != printed {printed[first_votes:]}")
        if got[:first_votes] != printed[:first_votes]:
            notes.append(f"{name}: registration/ballots parsed {got[:first_votes]} != printed {printed[:first_votes]}")
    return errors, notes


def by_location(block):
    """Sum a contest's precincts by LOCATION. Returns {location: {"registration", "ballots", "votes": [..]}}."""
    out = defaultdict(lambda: {"registration": 0, "ballots": 0, "votes": None})
    for r in block["precincts"]:
        o = out[r["location"]]
        o["registration"] += r["registration"]
        o["ballots"] += r["total"][0]
        votes = r["total"][1:]
        o["votes"] = votes if o["votes"] is None else [a + b for a, b in zip(o["votes"], votes)]
    return dict(out)
