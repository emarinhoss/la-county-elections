"""Statement of Votes Cast (precinct PDF) -> city totals for countywide contests, with checks.

City of each precinct = where its SHAPE sits (tools.precinct_geo): the city polygon covering most of it, or unincorporated.
Contest titles, layer city codes and place names are NOT used to decide, because each proved unreliable on the 2024 file:
  - a contest titled "LOS ANGELES CITY ..." (Measure LL) lists 986 precincts where the other Los Angeles measures list 805,
    and includes South Gate precincts and unincorporated areas, so appearing in it does not mean being in the city;
  - the layer's city code ZZ is the unincorporated catch-all and LM mixes Lomita with Los Angeles.
They are kept only as cross-checks, and we report how often they agree with the geometry:
  - contest check: precincts listed in a city's own contest vs the geometric city (disagreements are listed);
  - location rule:  precinct LOCATION text equal to a city name vs the geometric city.
A precinct missing from the layer falls back to its LOCATION text if that equals a city name, else "UNASSIGNED: <place>".

A block is "countywide" if it covers at least 90% of all precincts in the file. For each we sum precincts by city and
require the vote columns to equal the PDF's printed GRAND TOTAL exactly. That proves the parse is complete; it does not
prove the city assignment (that is what the geometry and the cross-checks are for).

Usage: python -m tools.svc_pipeline <pdf> <precinct_city_geo.csv> <boundary_geojson> <out_dir>
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

UNINC = "UNINCORPORATED: "
UNASSIGNED = "UNASSIGNED: "


def load_geo(path):
    """(exact id -> (city or None, share), 7-digit base -> set of cities). A blank city means unincorporated."""
    by_id, by_base = {}, defaultdict(set)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            city = r["city"] or None
            by_id[r["PRECINCT"]] = (city, float(r["overlap_share"] or 0))
            by_base[r["PRECINCT"][:7]].add(city)
    return by_id, by_base


def geo_lookup(pid, geo):
    """(city or None, share, 'exact'|'base') or None. Base fallback only if every layer precinct with that base agrees."""
    by_id, by_base = geo
    if pid in by_id:
        return by_id[pid][0], by_id[pid][1], "exact"
    cities = by_base.get(pid[:7])
    if cities and len(cities) == 1:
        return next(iter(cities)), None, "base"
    return None


def load_boundary_cities(geojson_path):
    """{city key: city name} for the incorporated cities in the boundary layer."""
    data = json.loads(Path(geojson_path).read_text())
    names = {f["properties"]["CITY_NAME"] for f in data["features"] if f["properties"].get("CITY_TYPE") == "City"}
    return {city_key(n): n for n in names}


def city_from_title(title, boundary):
    """City name if the title is a municipal contest of a boundary-layer city, else None."""
    parsed = parse_city_title(title)
    if not parsed:
        return None
    for candidate in (parsed[0], parsed[0] + " CITY"):  # "CARSON CITY ..." can mean Carson; "CULVER CITY ..." means Culver City
        if city_key(candidate) in boundary:
            return boundary[city_key(candidate)]
    return None


def countywide_blocks(blocks, threshold=0.9):
    """Blocks covering at least `threshold` of all precincts seen in the file. Adds precinct_share to every block."""
    all_ids = {r["precinct"] for b in blocks for r in b["precincts"]}
    out = []
    for b in blocks:
        share = len({r["precinct"] for r in b["precincts"]}) / len(all_ids) if all_ids else 0
        b["precinct_share"] = round(share, 3)
        if share >= threshold:
            out.append(b)
    return out


def contest_evidence(blocks, boundary):
    """{precinct: city} for precincts listed in exactly one city's own contest (a cross-check only), and the conflicts."""
    seen = defaultdict(Counter)
    for b in blocks:
        city = city_from_title(b["title"], boundary)
        if city:
            for r in b["precincts"]:
                seen[r["precinct"]][city] += 1
    return ({p: next(iter(c)) for p, c in seen.items() if len(c) == 1},
            {p: dict(c) for p, c in seen.items() if len(c) > 1})


def assign_all(blocks, geo, boundary):
    """{precinct: {location, city, method, share, contest_city}} for every precinct, plus the cross-check numbers."""
    contest, conflicts = contest_evidence(blocks, boundary)
    locs = defaultdict(Counter)
    for b in blocks:
        for r in b["precincts"]:
            locs[r["precinct"]][r["location"]] += 1
    table = {}
    for pid, c in locs.items():
        location = c.most_common(1)[0][0]
        hit = geo_lookup(pid, geo)
        if hit:
            city, share, how = hit
            suffix = "" if how == "exact" else "_base"
            label, method = (city, "geo" + suffix) if city else (UNINC + location, "geo_unincorporated" + suffix)
        elif city_key(location) in boundary:
            label, method, share = boundary[city_key(location)], "location", None
        else:
            label, method, share = UNASSIGNED + location, "unassigned", None
        table[pid] = {"location": location, "city": label, "method": method, "share": share, "contest_city": contest.get(pid, "")}

    def geo_city(t):  # the geometric city, or "(unincorporated)"
        return "(unincorporated)" if t["city"].startswith(UNINC) else t["city"]
    geo_known = {p: t for p, t in table.items() if t["method"].startswith("geo")}
    pairs, agree, both = Counter(), 0, 0
    for p, t in geo_known.items():
        if t["contest_city"]:
            both += 1
            pairs[(geo_city(t), t["contest_city"])] += 1
            agree += geo_city(t) == t["contest_city"]
    loc_applies = [t for t in geo_known.values() if city_key(t["location"]) in boundary]
    loc_correct = sum(boundary[city_key(t["location"])] == t["city"] for t in loc_applies)
    straddling = sum(1 for t in geo_known.values() if t["share"] is not None and t["share"] < 0.9 and not t["city"].startswith(UNINC))
    return table, {"conflicts": conflicts, "contest_pairs": pairs, "contest_both": both, "contest_agree": agree,
                   "location_applies": len(loc_applies), "location_correct": loc_correct, "straddling": straddling}


def city_reconciliation(blocks, boundary, geo_registration):
    """For each city with contests in the file, compare the registration its own contests report with the registration of the
    precincts the geometry put in that city. Reference = the most common registration among the city's larger contests (a
    district-only or wider contest differs from it and is outvoted); ties go to the larger number."""
    by_city = defaultdict(list)
    for b in blocks:
        city = city_from_title(b["title"], boundary)
        if city and b["precincts"]:
            grand = b["totals"].get("GRAND TOTAL")
            by_city[city].append((grand[0] if grand else sum(r["registration"] for r in b["precincts"]), b["title"]))
    rows = []
    for city, items in sorted(by_city.items()):
        top = max(reg for reg, _ in items)
        ref = max(Counter(reg for reg, _ in items if reg >= 0.5 * top).items(), key=lambda kv: (kv[1], kv[0]))[0]
        geo = geo_registration.get(city, 0)
        rows.append({"city": city, "contests": len(items), "reference_registration": ref, "largest_contest_registration": top,
                     "geometric_registration": geo, "difference_pct": round(100 * (geo - ref) / ref, 2) if ref else None})
    return rows


def aggregate_by_city(block, table):
    """Sum a block's precincts by assigned city. Also tracks ballots by assignment method."""
    out = defaultdict(lambda: {"registration": 0, "ballots": 0, "votes": None, "precincts": 0, "by_method": Counter()})
    for r in block["precincts"]:
        a = table[r["precinct"]]
        o = out[a["city"]]
        o["registration"] += r["registration"]
        o["ballots"] += r["total"][0]
        o["by_method"][a["method"]] += r["total"][0]
        votes = r["total"][1:]
        o["votes"] = votes if o["votes"] is None else [x + y for x, y in zip(o["votes"], votes)]
        o["precincts"] += 1
    return dict(out)


def run(text, geo_csv, boundary_geojson, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    geo, boundary = load_geo(geo_csv), load_boundary_cities(boundary_geojson)
    blocks = list(parse(text))
    if not blocks:
        raise SystemExit("no contest blocks found: the PDF layout is not the one this parser knows")

    checks = []
    for b in blocks:
        errors, notes = check_block(b)
        checks.append({"seq": b["seq"], "title": b["title"], "precincts": len(b["precincts"]), "precinct_share": None,
                       "errors": len(errors), "notes": len(notes), "first_error": (errors[0] if errors else "")[:160]})
    table, diag = assign_all(blocks, geo, boundary)
    county = countywide_blocks(blocks)
    for c, b in zip(checks, blocks):
        c["precinct_share"] = b["precinct_share"]

    rows, sumchecks = [], []
    geo_registration = {}
    for k, b in enumerate(county):
        agg = aggregate_by_city(b, table)
        if k == 0:
            geo_registration = {c: v["registration"] for c, v in agg.items()}
        width = max(len(v["votes"]) for v in agg.values())
        summed = [sum(v["votes"][i] for v in agg.values()) for i in range(width)]
        printed = b["totals"].get("GRAND TOTAL")
        ballots = sum(v["ballots"] for v in agg.values())
        fallback = sum(v["by_method"]["location"] + v["by_method"]["unassigned"] for v in agg.values())
        sumchecks.append({"seq": b["seq"], "title": b["title"], "choices": width, "printed_votes": (printed or [])[2:], "summed_votes": summed,
                          "votes_match_printed": bool(printed) and printed[2:] == summed,
                          "share_fallback": round(fallback / ballots, 4) if ballots else None})
        for city, v in sorted(agg.items()):
            geo_b = sum(n for m, n in v["by_method"].items() if m.startswith("geo"))
            rows.append({"seq": b["seq"], "title": b["title"], "city": city, "precincts": v["precincts"],
                         "registration": v["registration"], "ballots": v["ballots"], "ballots_geo": geo_b, "ballots_fallback": v["ballots"] - geo_b,
                         **{f"choice_{i + 1}": x for i, x in enumerate(v["votes"])}})

    def write(name, data, fields):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
    maxc = max((r["choices"] for r in sumchecks), default=0)
    write("block_checks.csv", checks, ["seq", "title", "precincts", "precinct_share", "errors", "notes", "first_error"])
    write("precinct_city.csv", [{"precinct": p, **t} for p, t in sorted(table.items())], ["precinct", "location", "city", "method", "share", "contest_city"])
    write("geo_vs_contest.csv", [{"geometric_city": g, "contest_city": c, "precincts": n} for (g, c), n in diag["contest_pairs"].most_common()],
          ["geometric_city", "contest_city", "precincts"])
    write("countywide_by_city.csv", rows, ["seq", "title", "city", "precincts", "registration", "ballots", "ballots_geo", "ballots_fallback"]
          + [f"choice_{i + 1}" for i in range(maxc)])
    recon = city_reconciliation(blocks, boundary, geo_registration)
    write("city_reconciliation.csv", recon, ["city", "contests", "reference_registration", "largest_contest_registration",
                                             "geometric_registration", "difference_pct"])
    write("countywide_checks.csv", [{**x, "printed_votes": json.dumps(x["printed_votes"]), "summed_votes": json.dumps(x["summed_votes"])} for x in sumchecks],
          ["seq", "title", "choices", "printed_votes", "summed_votes", "votes_match_printed", "share_fallback"])

    methods = Counter(t["method"] for t in table.values())
    rate = lambda a, b: round(a / b, 4) if b else None
    disagreements = [(g, c, n) for (g, c), n in diag["contest_pairs"].most_common() if g != c]
    summary = {
        "blocks": len(blocks), "blocks_with_errors": sum(c["errors"] > 0 for c in checks), "blocks_with_notes": sum(c["notes"] > 0 for c in checks),
        "unique_precincts": len(table), "precinct_methods": dict(methods),
        "precincts_with_geometry": sum(1 for t in table.values() if t["method"].startswith("geo")),
        "precincts_straddling_city_lines_under_90pct": diag["straddling"],
        "contest_vs_geometry": {"precincts_compared": diag["contest_both"], "agree": diag["contest_agree"],
                                "agreement": rate(diag["contest_agree"], diag["contest_both"]), "top_disagreements": disagreements[:12]},
        "location_rule_vs_geometry": {"applies": diag["location_applies"], "correct": diag["location_correct"],
                                      "accuracy": rate(diag["location_correct"], diag["location_applies"])},
        "contests_where_a_precinct_is_in_two_cities": len(diag["conflicts"]),
        "reconciliation": {"cities": len(recon),
                           "within_1pct": sum(1 for r in recon if r["difference_pct"] is not None and abs(r["difference_pct"]) <= 1),
                           "within_5pct": sum(1 for r in recon if r["difference_pct"] is not None and abs(r["difference_pct"]) <= 5),
                           "largest_differences": [(r["city"], r["difference_pct"]) for r in sorted(
                               recon, key=lambda r: -abs(r["difference_pct"] or 0))[:10]]},
        "boundary_cities": len(boundary),
        "boundary_cities_with_precincts": len({t["city"] for t in table.values() if t["city"] in boundary.values()}),
        "countywide_blocks": [{"seq": x["seq"], "title": x["title"], "match": x["votes_match_printed"], "share_fallback": x["share_fallback"]} for x in sumchecks],
        "countywide_all_match": all(x["votes_match_printed"] for x in sumchecks) if sumchecks else False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    cv, lr = summary["contest_vs_geometry"], summary["location_rule_vs_geometry"]
    lines = ["## SVC rehearsal (city from precinct geometry)",
             f"- contest blocks parsed: **{summary['blocks']}** ({summary['blocks_with_errors']} with errors, {summary['blocks_with_notes']} with notes)",
             f"- unique precincts: {len(table):,}; assigned by: {dict(methods)}",
             f"- precincts under 90% inside their city (straddle a city line): {diag['straddling']}",
             f"- contest evidence vs geometry: {cv['agree']}/{cv['precincts_compared']} agree ({cv['agreement']}); top disagreements (geometry, contest, n): {cv['top_disagreements'][:6]}",
             f"- registration in each city's own contests vs the geometric city: {summary['reconciliation']['within_1pct']} of "
             f"{summary['reconciliation']['cities']} within 1%, {summary['reconciliation']['within_5pct']} within 5%; largest differences: "
             f"{summary['reconciliation']['largest_differences'][:6]}",
             f"- place-name rule vs geometry: {lr['correct']}/{lr['applies']} correct ({lr['accuracy']})",
             f"- boundary cities with at least one precinct: {summary['boundary_cities_with_precincts']} of {summary['boundary_cities']}",
             f"- countywide blocks: {len(sumchecks)}; vote totals equal the printed GRAND TOTAL in all: **{summary['countywide_all_match']}**"]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    return summary


def pdf_text(pdf):
    with tempfile.NamedTemporaryFile("w+", suffix=".txt") as tmp:
        subprocess.run(["pdftotext", "-layout", str(pdf), tmp.name], check=True)
        return Path(tmp.name).read_text()


if __name__ == "__main__":
    pdf, geo_csv, boundary, out_dir = sys.argv[1:5]
    run(pdf_text(pdf), geo_csv, boundary, out_dir)
    print((Path(out_dir) / "summary.md").read_text())
