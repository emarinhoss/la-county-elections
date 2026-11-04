# LA County election dashboard: spec v0

Scope for v1: the **Nov 3, 2026 general election**, all contests and measures. Other elections come later,
so nothing may hard-code the election date. Output is a public static site. Collection runs on GitHub Actions.

## Rules

- Public repo, open data only. No secrets, no voter files (those are sold by the county and contain personal data).
- Never invent numbers. Everything shown comes from a recorded snapshot. If a source was not fetched, say so.
- Raw snapshots are immutable. Parsing never edits them.
- Every derived table records the snapshot id it came from, so any chart can be reproduced.
- Estimates (late-count projection) are labeled as estimates, with assumptions and an uncertainty range.
- Correlations with demographics are ecological. The UI must say they do not describe individual voters.

## Pipeline

1. `collect/`: download the county result files on a schedule. Save to `data/raw/<election>/<UTC timestamp>/`
   with a manifest (URL, HTTP status, sha256, bytes). Skip the save if the hash equals the previous one.
2. `parse/`: raw files to tidy tables (below). One parser per source format, each with a fixture-based test.
3. `build/`: tidy tables to static JSON/GeoJSON in `site/data/`, then the site.
4. `site/`: static HTML/JS (MapLibre or Leaflet + a chart library), deployed to GitHub Pages.

A GitHub Action runs collect, parse and build every 15-30 minutes, commits new snapshots, and deploys.

## Tidy tables

- `contests`: contest_id, name, type (office | measure), jurisdiction, geography_level (county | city | district | precinct), vote_for
- `choices`: contest_id, choice_id, label, party (if any)
- `results`: snapshot_id, contest_id, choice_id, geo_id, votes
- `turnout`: snapshot_id, geo_id, registered, ballots_cast, (ballots_outstanding if published)
- `snapshots`: snapshot_id, fetched_at, source_url, sha256, county_reported_timestamp
- `geographies`: geo_id, level, name, source

## Geography

- Cities: Census TIGER places or the county GIS layer (pick one at first fetch and record why).
  Unincorporated areas get their own polygon so the map has no holes.
- Districts (congressional, senate, assembly, supervisorial, school): from the county or state source.
- Precincts: county ArcGIS feature service, used once precinct results are published.
- Countywide contests by city need either county city-level reports or a precinct-to-city crosswalk.
  Which one the county provides is **unverified**. The first fetch settles it.

## Open items (verify on first real fetch)

- Current URL, format and update cadence of the RR/CC live results (is there a JSON feed behind the page?).
- Whether city-level breakdowns of countywide contests are published before certification.
- Whether ballots-outstanding estimates are machine-readable.
- Licence and terms for each source. Record them in `docs/sources.md`.

## Analyses

**Phase 1 (live):** contest picker + choropleth + results table; count trajectory per contest from snapshots;
data-QA flags (totals that decrease between snapshots).
**Phase 2:** turnout by city; measure support vs candidate support; roll-off (undervote) on measures.
**Phase 3 (needs past elections):** swing vs 2022/2024, late-count shift and projected final margin
with an uncertainty range, city clustering, spatial autocorrelation, ACS correlations.

## Milestones

- M0: this spec, repo skeleton, source inventory with real URLs (needs a machine with open internet).
- M1: collector + parser for one contest type, run once by hand, then on a schedule.
- M2: map + contest picker for all contests.
- M3: time series and QA flags.
- M4+: analytics phases above.

## Environment note

The Claude Code cloud sandbox used to write this spec could not reach county, Census or Secretary of State hosts
(proxy blocked). Parsers are developed against fixtures. The first real fetch happens in GitHub Actions.

## Countywide contests by city (status: waiting on county data)

What we know (Nov 4, 2026):
- The live results API gives county totals only. No city or precinct breakdown is in the API or in the results app code.
- City-level numbers for countywide contests come from the Statement of Votes Cast (SVC), published after
  certification (early December for past general elections). Files live under `content.lavote.gov/docs/rrcc/svc/`
  and, for past elections, start with the election id (e.g. `4324_...` for the 2024 general). For 2026 the id is 4348.
  Only `4324_final_svc_district_v3.pdf` was seen in a web search. The other file names in `config/sources.json`
  are guesses, and 2026 files are expected to 404 until certification.
- The collector probes these URLs (HEAD only, nothing stored) every run, so the log shows when a file appears.

Plan once a precinct-level file exists:
1. Parse it into `precinct_results(contest_id, precinct, choice, votes)`.
2. Map precincts to cities with `CITY_EST` from the county precinct layer (33,219 polygons).
3. Sum by city and show it on the map for countywide contests, labelled "from precinct data, as of <date>".

Risks to check, not assumed away:
- The SVC may report consolidated precincts (the election data says 2,853) while the layer has 33,219 polygons.
  We need a crosswalk between them. If none is published, city totals cannot be computed exactly.
- `CITY_EST` is an estimate. A precinct can straddle a city boundary. Report how many votes sit in such precincts.
- Check: precinct sums per contest must equal the county total before any city number is shown.
- The SVC format (PDF vs Excel/CSV) is unknown. A PDF parser is a larger job than an Excel one.

### What the 2024 SVC precinct PDF looks like (read from real sample pages, Nov 4, 2026)

Source: `4324_final_svc_precinct_public.pdf`, 61 MB, 6,190 pages, text-based (Microsoft Reporting Services).
Samples are committed under `data/samples/svc/4324_final_svc_precinct_public/`; parser: `tools/svc_parse.py`.
- Every contest is a block: a title, then one three-row entry per precinct (in-person, VOTE BY MAIL, TOTAL),
  then PRECINCT TOTAL / VBM TOTAL / GRAND TOTAL rows. So every contest has a check against its own totals.
- The precinct label is `<LOCATION> - <7-digit id + letter>[*]`. LOCATION is a **community**, not always a city:
  CARSON, POMONA, TORRANCE, but also SUNLAND (a neighborhood inside the City of Los Angeles) and unincorporated
  places such as WEST ATHENS. LOCATION alone is therefore not a city. The city must come from the precinct id
  through the county precinct layer (`CITY_EST`). The layer's id format is not yet known (probes added).
- Candidate names wrap over several header lines. The parser ignores them and keeps vote columns in order. Columns
  are then matched to the API's choice order for the same contest, and the contest total is checked against the API.
- The API's contest titles use the same wording as the PDF (`STATE SENATOR, 35th District`, `STATE MEASURE 5`).
- On the one contest we can check completely (Carson mayor, 26 precincts), all vote columns match the printed totals
  exactly. Registration and ballots cast in the county's printed totals are each 1 above the sum of the listed
  precincts. We report such gaps as notes and keep the check strict on votes.
- The 26 precinct rows in that contest all parsed. Other layouts (multi-seat races, retention votes, write-in
  columns) have not been seen yet.
- Unincorporated polygons in the boundary layer are all named just "Unincorporated", so unincorporated
  communities cannot be separate map shapes.
