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
