"""Statement of Votes Cast (precinct PDF) -> city totals for countywide contests, with checks.

Steps:
 1. pdftotext the whole PDF and parse every contest block (tools.svc_parse).
 2. Join each precinct to the county precinct layer by exact id (fallback: first 7 digits). The layer gives DST_CITY,
    a short city CODE.
 3. Name the codes. A code is named from the city contests in the same PDF: the precincts of the block titled
    "CARSON CITY GENERAL MUNICIPAL ELECTION ..." carry the code that means Carson. Otherwise from the LOCATION text if it
    equals a boundary-layer city name. Codes we cannot name stay "UNNAMED:<code>" and are reported, never guessed.
 4. A block is "countywide" if it covers at least 90% of all precincts seen in the file. For each, sum precincts by city
    and require the vote columns to equal the PDF's printed GRAND TOTAL exactly.

Usage: python -m tools.svc_pipeline <pdf> <precinct_layer.csv> <boundary_geojson> <out_dir>
"""
import csv
import json
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from sitegen.city_contests import city_key, parse_city_title
from tools.svc_parse import check_block, parse

UNMATCHED = "UNMATCHED ID"
BLANK = "(blank)"


def load_layer(path):
    """(exact id -> code, 7-digit base -> most common code)."""
    by_id, by_base = {}, defaultdict(Counter)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            code = r["DST_CITY"] or BLANK
            by_id[r["PRECINCT"]] = code
            by_base[r["CITY_EST"]][code] += 1
    return by_id, {k: c.most_common(1)[0][0] for k, c in by_base.items()}


def map_precinct(pid, layer):
    by_id, by_base = layer
    if pid in by_id:
        return by_id[pid], "exact"
    if pid[:7] in by_base:
        return by_base[pid[:7]], "base"
    return None, "unmatched"


def load_boundary_cities(geojson_path):
    """{city key: city name} for the 88 incorporated cities in the boundary layer."""
    data = json.loads(Path(geojson_path).read_text())
    names = {f["properties"]["CITY_NAME"] for f in data["features"] if f["properties"].get("CITY_TYPE") == "City"}
    return {city_key(n): n for n in names}


def city_from_title(title, boundary):
    """City name if the title is a municipal contest of a boundary-layer city, else None."""
    parsed = parse_city_title(title)
    if not parsed:
        return None
    name = parsed[0]
    for candidate in (name, name + " CITY"):  # "CARSON CITY ..." can mean Carson; "CULVER CITY ..." means Culver City
        if city_key(candidate) in boundary:
            return boundary[city_key(candidate)]
    return None


def build_code_table(blocks, layer, boundary):
    """{code: {city, method, precincts, confidence, top_locations}}"""
    named, locs = defaultdict(Counter), defaultdict(Counter)
    for b in blocks:
        city = city_from_title(b["title"], boundary)
        for r in b["precincts"]:
            code, _ = map_precinct(r["precinct"], layer)
            if code is None:
                continue
            locs[code][r["location"]] += 1
            if city:
                named[code][city] += 1
    table = {}
    for code, c in named.items():
        city, n = c.most_common(1)[0]
        table[code] = {"city": city, "method": "city_contest", "precincts": sum(c.values()),
                       "confidence": round(n / sum(c.values()), 3), "top_locations": locs[code].most_common(3)}
    for code, c in locs.items():
        if code in table:
            continue
        loc, n = c.most_common(1)[0]
        share = n / sum(c.values())
        if city_key(loc) in boundary and share >= 0.8:
            table[code] = {"city": boundary[city_key(loc)], "method": "location_text", "precincts": sum(c.values()),
                           "confidence": round(share, 3), "top_locations": c.most_common(3)}
        else:
            table[code] = {"city": None, "method": "unnamed", "precincts": sum(c.values()),
                           "confidence": 0.0, "top_locations": c.most_common(3)}
    return table


def countywide_blocks(blocks, threshold=0.9):
    all_ids = {r["precinct"] for b in blocks for r in b["precincts"]}
    out = []
    for b in blocks:
        share = len({r["precinct"] for r in b["precincts"]}) / len(all_ids) if all_ids else 0
        b["precinct_share"] = round(share, 3)
        if share >= threshold:
            out.append(b)
    return out


def aggregate_by_city(block, layer, table):
    """Sum a block's precincts by city. Unnamed codes and unmatched ids get their own labelled groups."""
    out = defaultdict(lambda: {"registration": 0, "ballots": 0, "votes": None, "precincts": 0})
    for r in block["precincts"]:
        code, _ = map_precinct(r["precinct"], layer)
        if code is None:
            label = UNMATCHED
        else:
            label = table[code]["city"] or f"UNNAMED:{code}"
        o = out[label]
        o["registration"] += r["registration"]
        o["ballots"] += r["total"][0]
        votes = r["total"][1:]
        o["votes"] = votes if o["votes"] is None else [a + b for a, b in zip(o["votes"], votes)]
        o["precincts"] += 1
    return dict(out)


def run(text, layer_csv, boundary_geojson, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    layer, boundary = load_layer(layer_csv), load_boundary_cities(boundary_geojson)
    blocks = list(parse(text))
    if not blocks:
        raise SystemExit("no contest blocks found: the PDF layout is not the one this parser knows")

    # per-block self checks
    checks = []
    for b in blocks:
        errors, notes = check_block(b)
        checks.append({"seq": b["seq"], "title": b["title"], "precincts": len(b["precincts"]),
                       "precinct_share": None, "errors": len(errors), "notes": len(notes),
                       "first_error": (errors[0] if errors else "")[:160]})
    table = build_code_table(blocks, layer, boundary)
    county = countywide_blocks(blocks)
    for c, b in zip(checks, blocks):
        c["precinct_share"] = b["precinct_share"]

    # precinct match quality, over the whole file
    methods = Counter(map_precinct(r["precinct"], layer)[1] for b in blocks for r in b["precincts"])
    rows, sumchecks = [], []
    for b in county:
        agg = aggregate_by_city(b, layer, table)
        width = max(len(v["votes"]) for v in agg.values())
        summed = [sum(v["votes"][i] for v in agg.values()) for i in range(width)]
        printed = b["totals"].get("GRAND TOTAL")
        ballots = sum(v["ballots"] for v in agg.values())
        bad = sum(v["ballots"] for k, v in agg.items() if k == UNMATCHED or k.startswith("UNNAMED:"))
        sumchecks.append({"seq": b["seq"], "title": b["title"], "choices": width,
                          "printed_votes": (printed or [])[2:], "summed_votes": summed,
                          "votes_match_printed": bool(printed) and printed[2:] == summed,
                          "ballots_unnamed_or_unmatched": bad, "share_unnamed_or_unmatched": round(bad / ballots, 4) if ballots else None})
        for city, v in sorted(agg.items()):
            rows.append({"seq": b["seq"], "title": b["title"], "city": city, "precincts": v["precincts"],
                         "registration": v["registration"], "ballots": v["ballots"],
                         **{f"choice_{i + 1}": x for i, x in enumerate(v["votes"])}})

    def write(name, data, fields):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
    maxc = max((r["choices"] for r in sumchecks), default=0)
    write("block_checks.csv", checks, ["seq", "title", "precincts", "precinct_share", "errors", "notes", "first_error"])
    write("code_to_city.csv", [{"code": c, **{k: (json.dumps(v) if k == "top_locations" else v) for k, v in t.items()}}
                               for c, t in sorted(table.items())],
          ["code", "city", "method", "precincts", "confidence", "top_locations"])
    write("countywide_by_city.csv", rows, ["seq", "title", "city", "precincts", "registration", "ballots"] + [f"choice_{i + 1}" for i in range(maxc)])
    write("countywide_checks.csv", [{**s, "printed_votes": json.dumps(s["printed_votes"]), "summed_votes": json.dumps(s["summed_votes"])} for s in sumchecks],
          ["seq", "title", "choices", "printed_votes", "summed_votes", "votes_match_printed", "ballots_unnamed_or_unmatched", "share_unnamed_or_unmatched"])

    total = sum(methods.values())
    summary = {
        "blocks": len(blocks), "blocks_with_errors": sum(c["errors"] > 0 for c in checks),
        "blocks_with_notes": sum(c["notes"] > 0 for c in checks),
        "precinct_rows": total, "match_exact": methods["exact"], "match_base_only": methods["base"], "match_none": methods["unmatched"],
        "codes": len(table), "codes_named": sum(t["city"] is not None for t in table.values()),
        "codes_unnamed": sorted(c for c, t in table.items() if t["city"] is None),
        "named_cities": len({t["city"] for t in table.values() if t["city"]}), "boundary_cities": len(boundary),
        "countywide_blocks": [{"seq": s["seq"], "title": s["title"], "match": s["votes_match_printed"],
                               "unnamed_or_unmatched_share": s["share_unnamed_or_unmatched"]} for s in sumchecks],
        "countywide_all_match": all(s["votes_match_printed"] for s in sumchecks) if sumchecks else False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["## SVC rehearsal", f"- contest blocks parsed: **{summary['blocks']}** ({summary['blocks_with_errors']} with errors, "
             f"{summary['blocks_with_notes']} with notes)",
             f"- precinct rows: {total:,} (exact id match {methods['exact']:,}, 7-digit fallback {methods['base']:,}, no match {methods['unmatched']:,})",
             f"- city codes: {summary['codes']} ({summary['codes_named']} named, {len(summary['codes_unnamed'])} unnamed: {', '.join(summary['codes_unnamed'][:20])})",
             f"- boundary cities named by a code: {summary['named_cities']} of {summary['boundary_cities']}",
             f"- countywide blocks: {len(sumchecks)}; vote totals equal the printed GRAND TOTAL in all of them: **{summary['countywide_all_match']}**"]
    for s in sumchecks:
        lines.append(f"  - {s['title']}: match={s['votes_match_printed']}, share of ballots in unnamed/unmatched = {s['share_unnamed_or_unmatched']}")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return summary


def pdf_text(pdf):
    with tempfile.NamedTemporaryFile("w+", suffix=".txt") as tmp:
        subprocess.run(["pdftotext", "-layout", str(pdf), tmp.name], check=True)
        return Path(tmp.name).read_text()


if __name__ == "__main__":
    pdf, layer_csv, boundary, out_dir = sys.argv[1:5]
    s = run(pdf_text(pdf), layer_csv, boundary, out_dir)
    print((Path(out_dir) / "summary.md").read_text())
