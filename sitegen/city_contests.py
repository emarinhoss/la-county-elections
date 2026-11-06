"""Build site/data/city_contests.json: every city contest with its latest county numbers.

Input:  data/tidy/<election>/{contests,choices,results,election}.csv   (written by parse.election)
Output: one record per city, each with its contests and choices (votes and share of votes in that contest).

City contests are the "Cities" group of the county's contest list. The city name is read from the
contest title. Numbers are unofficial partial counts until the county certifies.
"""
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

from sitegen.measure_title import measure_title

NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}

# "CITY OF ALHAMBRA GENERAL MUNICIPAL ELECTION ..." / "LOS ANGELES CITY GENERAL ..." /
# "CITY OF PASADENA REGULAR MUNICIPAL ELECTION ..." / "... SPECIAL MUNICIPAL ELECTION - MEASURE DB"
TITLE = re.compile(
    r"^(?:CITY OF\s+)?(?P<city>.+?)"
    r"\s+(?:(?:REGULAR|GENERAL|SPECIAL|NOMINATING)\s+)?(?:MUNICIPAL\s+)?(?:ELECTION|PRIMARY|RUNOFF)"
    r"\b[\s-]*(?P<rest>.*)$"
)


def city_key(name):
    """'La Cañada Flintridge' and 'LA CANADA FLINTRIDGE' give the same key."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]+", "", s.lower())


def parse_city_title(title):
    """Return (city name, contest label) from a county city-contest title, or None."""
    m = TITLE.match(title.strip())
    if not m:
        return None
    rest = re.sub(r"^NOMINATING ELECTION\s*", "", m.group("rest").strip()).strip(" -")
    city = m.group("city").strip()
    # "LOS ANGELES CITY ..." names the city with a trailing CITY, but "CITY OF CULVER CITY" keeps its own.
    if not title.strip().startswith("CITY OF") and city.endswith(" CITY"):
        city = city[: -len(" CITY")]
    return city, rest or title.strip()


def parse_vote_for(text):
    """'Vote for no more than three' -> 3. Blank means 1 (checked: city votes never exceed ballots)."""
    for word, n in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text or "", re.I):
            return n
    return 1


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def contest_record(c, label, choice_rows, votes, ballots):
    """One contest as shown on the site. Shares are of votes counted in this contest."""
    rows = [{"name": ch["name"], "party": ch["party"], "votes": votes[ch["choice_id"]]} for ch in choice_rows]
    total = sum(r["votes"] for r in rows)
    for r in rows:
        r["share"] = round(r["votes"] / total, 4) if total else None
    rec = {
        "id": int(c["contest_id"]), "label": label, "kind": c["type"].lower(),
        "vote_for": parse_vote_for(c["vote_for"]), "pass_rate": c["pass_rate"],
        "ballots_cast": ballots.get(c["contest_id"]), "total_votes": total, "choices": rows,
    }
    if c.get("measure_text"):          # the county's own words: full text, and a one-sentence title taken from it
        rec["measure_text"] = c["measure_text"]
        rec["measure_title"] = measure_title(c["measure_text"])
    return rec


def latest_numbers(tidy):
    """(latest snapshot id, county time, votes by choice_id, ballots by contest_id)."""
    results = read_csv(tidy / "results.csv")
    latest = max(r["snapshot"] for r in results)
    votes = {r["choice_id"]: int(r["votes"]) for r in results if r["snapshot"] == latest}
    county_time = next(r["county_time"] for r in results if r["snapshot"] == latest)
    ballots = {r["contest_id"]: int(r["value"]) for r in read_csv(tidy / "contest_counters.csv")
               if r["snapshot"] == latest and r["counter"] == "CBLT"}
    return latest, county_time, votes, ballots


def build(tidy_dir):
    tidy = Path(tidy_dir)
    info = json.loads((tidy / "election.json").read_text())
    contests = [c for c in read_csv(tidy / "contests.csv") if c["group"] == "Cities"]
    choices = defaultdict(list)
    for ch in read_csv(tidy / "choices.csv"):
        choices[ch["contest_id"]].append(ch)
    latest, county_time, votes, ballots = latest_numbers(tidy)

    cities, unparsed = {}, []
    for c in contests:
        parsed = parse_city_title(c["title"])
        if not parsed:
            unparsed.append(c["title"])
            continue
        name, label = parsed
        city = cities.setdefault(city_key(name), {"key": city_key(name), "name": name.title(), "contests": []})
        city["contests"].append(contest_record(c, label, choices[c["contest_id"]], votes, ballots))
    for city in cities.values():
        city["contests"].sort(key=lambda x: (x["kind"] != "candidate", x["label"]))
    return {
        "election": {"title": info["title"], "date": info["date"]},
        "county_time": county_time, "snapshot": latest, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cities": sorted(cities.values(), key=lambda c: c["name"]),
        "unparsed_titles": unparsed,
    }


if __name__ == "__main__":
    election = sys.argv[1] if len(sys.argv) > 1 else "2026-11-03-general"
    out = build(f"data/tidy/{election}")
    dest = Path("site/data/city_contests.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    n = sum(len(c["contests"]) for c in out["cities"])
    print(f"{len(out['cities'])} cities, {n} contests, unparsed titles: {len(out['unparsed_titles'])}")
    sys.exit(1 if out["unparsed_titles"] else 0)
