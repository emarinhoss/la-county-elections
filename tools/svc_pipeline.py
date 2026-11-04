"""Statement of Votes Cast (precinct PDF) -> city totals for countywide contests, with checks.

Every precinct gets a city (or an honest "unincorporated or unknown" label) one precinct at a time:
 1. direct:   the precinct is listed in a city's own contest ("CARSON CITY GENERAL MUNICIPAL ELECTION ...").
              A precinct inside a city's contest belongs to that city. This beats any code or place name.
 2. code:     else, the precinct layer's city CODE (DST_CITY), but only if that code is "pure": at least 3 directly
              evidenced precincts carry it and at least 98% of them are the same city. Mixed codes are not used.
              (2024 rehearsal: code ZZ is the unincorporated catch-all and LM mixes Lomita with Los Angeles.)
 3. location: else, the precinct's LOCATION text if it equals a boundary-layer city name.
 4. otherwise it stays "UNINCORPORATED OR UNKNOWN: <LOCATION>". It is never guessed into a city.
The fallback rules (2 and 3) are scored on precincts where the direct answer is known, and that score is reported.
A block is "countywide" if it covers at least 90% of all precincts in the file. For each, we sum precincts by city and
require the vote columns to equal the PDF's printed GRAND TOTAL exactly. That check proves the parse is complete; it does
not prove the city assignment, which is what the direct/fallback score is for.

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


MIN_DIRECT_FOR_PURE, PURE_SHARE = 3, 0.98
UNASSIGNED = "UNINCORPORATED OR UNKNOWN: "


def direct_assignments(blocks, boundary):
    """{precinct id: city} from precincts listed in a city's own contest, plus {precinct id: {city: n}} for conflicts."""
    seen = defaultdict(Counter)
    for b in blocks:
        city = city_from_title(b["title"], boundary)
        if city:
            for r in b["precincts"]:
                seen[r["precinct"]][city] += 1
    direct = {p: next(iter(c)) for p, c in seen.items() if len(c) == 1}
    conflicts = {p: dict(c) for p, c in seen.items() if len(c) > 1}
    return direct, conflicts


def code_purity(direct, layer):
    """{code: {"precincts": n, "top_city", "top_share", "pure": bool, "cities": {...}}} from directly evidenced precincts."""
    by_code = defaultdict(Counter)
    for pid, city in direct.items():
        code, _ = map_precinct(pid, layer)
        if code is not None:
            by_code[code][city] += 1
    out = {}
    for code, c in by_code.items():
        n, (top, k) = sum(c.values()), c.most_common(1)[0]
        out[code] = {"precincts": n, "top_city": top, "top_share": round(k / n, 3), "cities": dict(c),
                     "pure": n >= MIN_DIRECT_FOR_PURE and k / n >= PURE_SHARE}
    return out


def fallback_city(code, location, purity, boundary, loo_city=None):
    """Rule 2 then rule 3. Returns (city, method) or (None, None). loo_city removes that precinct from the code evidence."""
    if code is not None and code in purity:
        cities = Counter(purity[code]["cities"])
        if loo_city:
            cities[loo_city] -= 1
        n = sum(v for v in cities.values() if v > 0)
        if n >= MIN_DIRECT_FOR_PURE:
            top, k = cities.most_common(1)[0]
            if k / n >= PURE_SHARE:
                return top, "code"
    if city_key(location) in boundary:
        return boundary[city_key(location)], "location"
    return None, None


def assign_all(blocks, layer, boundary):
    """{precinct id: {"location", "code", "city", "method"}} for every precinct in the file, plus diagnostics."""
    direct, conflicts = direct_assignments(blocks, boundary)
    locs = defaultdict(Counter)
    for b in blocks:
        for r in b["precincts"]:
            locs[r["precinct"]][r["location"]] += 1
    purity = code_purity(direct, layer)
    table, disagree = {}, 0
    for pid, c in locs.items():
        location = c.most_common(1)[0][0]
        code, _ = map_precinct(pid, layer)
        if pid in direct:
            city, method = direct[pid], "direct"
        else:
            city, method = fallback_city(code, location, purity, boundary)
            if method == "code" and city_key(location) in boundary and boundary[city_key(location)] != city:
                disagree += 1
            if city is None:
                city, method = UNASSIGNED + location, "unassigned"
        table[pid] = {"location": location, "code": code or "", "city": city, "method": method}
    # score the fallback rules where the direct answer is known (leave this precinct out of the code evidence)
    score = {"code_applies": 0, "code_correct": 0, "location_applies": 0, "location_correct": 0}
    for pid, city in direct.items():
        code, _ = map_precinct(pid, layer)
        location = table[pid]["location"]
        got, method = fallback_city(code, location, purity, {}, loo_city=city)  # code rule only
        if method == "code":
            score["code_applies"] += 1
            score["code_correct"] += got == city
        if city_key(location) in boundary:
            score["location_applies"] += 1
            score["location_correct"] += boundary[city_key(location)] == city
    return table, {"conflicts": conflicts, "purity": purity, "code_vs_location_disagreements": disagree, "fallback_score": score,
                   "direct_precincts": len(direct)}


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


def run(text, layer_csv, boundary_geojson, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    layer, boundary = load_layer(layer_csv), load_boundary_cities(boundary_geojson)
    blocks = list(parse(text))
    if not blocks:
        raise SystemExit("no contest blocks found: the PDF layout is not the one this parser knows")

    checks = []
    for b in blocks:
        errors, notes = check_block(b)
        checks.append({"seq": b["seq"], "title": b["title"], "precincts": len(b["precincts"]), "precinct_share": None,
                       "errors": len(errors), "notes": len(notes), "first_error": (errors[0] if errors else "")[:160]})
    table, diag = assign_all(blocks, layer, boundary)
    county = countywide_blocks(blocks)
    for c, b in zip(checks, blocks):
        c["precinct_share"] = b["precinct_share"]

    rows, sumchecks = [], []
    for b in county:
        agg = aggregate_by_city(b, table)
        width = max(len(v["votes"]) for v in agg.values())
        summed = [sum(v["votes"][i] for v in agg.values()) for i in range(width)]
        printed = b["totals"].get("GRAND TOTAL")
        ballots = sum(v["ballots"] for v in agg.values())
        weak = sum(v["by_method"]["unassigned"] for v in agg.values())
        inferred = sum(v["by_method"]["code"] + v["by_method"]["location"] for v in agg.values())
        sumchecks.append({"seq": b["seq"], "title": b["title"], "choices": width, "printed_votes": (printed or [])[2:],
                          "summed_votes": summed, "votes_match_printed": bool(printed) and printed[2:] == summed,
                          "share_unassigned": round(weak / ballots, 4) if ballots else None,
                          "share_inferred": round(inferred / ballots, 4) if ballots else None})
        for city, v in sorted(agg.items()):
            rows.append({"seq": b["seq"], "title": b["title"], "city": city, "precincts": v["precincts"],
                         "registration": v["registration"], "ballots": v["ballots"],
                         "ballots_direct": v["by_method"]["direct"], "ballots_inferred": v["by_method"]["code"] + v["by_method"]["location"],
                         "ballots_unassigned": v["by_method"]["unassigned"],
                         **{f"choice_{i + 1}": x for i, x in enumerate(v["votes"])}})

    def write(name, data, fields):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
    maxc = max((r["choices"] for r in sumchecks), default=0)
    write("block_checks.csv", checks, ["seq", "title", "precincts", "precinct_share", "errors", "notes", "first_error"])
    write("precinct_city.csv", [{"precinct": p, **t} for p, t in sorted(table.items())], ["precinct", "location", "code", "city", "method"])
    write("code_purity.csv", [{"code": c, **{k: (json.dumps(v) if k == "cities" else v) for k, v in d.items()}} for c, d in sorted(diag["purity"].items())],
          ["code", "precincts", "top_city", "top_share", "pure", "cities"])
    write("countywide_by_city.csv", rows, ["seq", "title", "city", "precincts", "registration", "ballots", "ballots_direct",
                                           "ballots_inferred", "ballots_unassigned"] + [f"choice_{i + 1}" for i in range(maxc)])
    write("countywide_checks.csv", [{**x, "printed_votes": json.dumps(x["printed_votes"]), "summed_votes": json.dumps(x["summed_votes"])} for x in sumchecks],
          ["seq", "title", "choices", "printed_votes", "summed_votes", "votes_match_printed", "share_unassigned", "share_inferred"])

    methods = Counter(t["method"] for t in table.values())
    sc = diag["fallback_score"]
    rate = lambda a, b: round(a / b, 4) if b else None
    cities_used = {t["city"] for t in table.values() if t["method"] != "unassigned"}
    unassigned = Counter()
    for r in rows:
        if r["seq"] == county[0]["seq"] and r["city"].startswith(UNASSIGNED):
            unassigned[r["city"][len(UNASSIGNED):]] += r["ballots"]
    summary = {
        "blocks": len(blocks), "blocks_with_errors": sum(c["errors"] > 0 for c in checks), "blocks_with_notes": sum(c["notes"] > 0 for c in checks),
        "unique_precincts": len(table), "precinct_methods": dict(methods),
        "precincts_not_in_layer": sum(1 for t in table.values() if not t["code"]),
        "direct_conflicts": len(diag["conflicts"]), "code_vs_location_disagreements": diag["code_vs_location_disagreements"],
        "codes_pure": sorted(c for c, d in diag["purity"].items() if d["pure"]),
        "codes_mixed": sorted(c for c, d in diag["purity"].items() if not d["pure"] and d["precincts"] >= MIN_DIRECT_FOR_PURE),
        "fallback_score": {**sc, "code_accuracy": rate(sc["code_correct"], sc["code_applies"]),
                           "location_accuracy": rate(sc["location_correct"], sc["location_applies"])},
        "boundary_cities": len(boundary), "boundary_cities_with_precincts": len({c for c in cities_used if city_key(c) in boundary}),
        "top_unassigned_in_first_countywide_block": unassigned.most_common(12),
        "countywide_blocks": [{"seq": x["seq"], "title": x["title"], "match": x["votes_match_printed"], "share_inferred": x["share_inferred"],
                               "share_unassigned": x["share_unassigned"]} for x in sumchecks],
        "countywide_all_match": all(x["votes_match_printed"] for x in sumchecks) if sumchecks else False,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["## SVC rehearsal", f"- contest blocks parsed: **{summary['blocks']}** ({summary['blocks_with_errors']} with errors, {summary['blocks_with_notes']} with notes)",
             f"- unique precincts: {len(table):,}; city assigned by: {dict(methods)}; not in the precinct layer: {summary['precincts_not_in_layer']}",
             f"- precincts in two different cities' contests (conflicts): {summary['direct_conflicts']}",
             f"- pure city codes: {len(summary['codes_pure'])}; mixed codes (not used): {', '.join(summary['codes_mixed']) or 'none'}",
             f"- fallback rules scored on precincts with a known answer: code rule {sc['code_correct']}/{sc['code_applies']} correct, "
             f"location-text rule {sc['location_correct']}/{sc['location_applies']} correct",
             f"- boundary cities with at least one precinct: {summary['boundary_cities_with_precincts']} of {summary['boundary_cities']}",
             f"- countywide blocks: {len(sumchecks)}; vote totals equal the printed GRAND TOTAL in all: **{summary['countywide_all_match']}**",
             f"- biggest unincorporated-or-unknown places (ballots, first countywide contest): {summary['top_unassigned_in_first_countywide_block']}"]
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
