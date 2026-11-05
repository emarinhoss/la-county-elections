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
2. Map precincts to cities through the county precinct layer (33,219 polygons). CORRECTION (probes, Nov 4): the layer's
   `CITY_EST` is NOT a city name. It is the first 7 digits of the precinct id. The city is in `DST_CITY`, a short code (see below).
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

### Precinct layer probes (read from real data, Nov 4, 2026)

- Layer `PRECINCT` ids have the same format as the SVC ids: 7 digits + a letter (`1030003A`). The Carson precinct
  `1030003A` from the 2024 PDF exists in the layer, and so does `1030003B`. So an SVC precinct can be joined to the layer
  by exact id. Fall back to the 7-digit base only if an exact id is missing, and count how many fall back.
- `CITY_EST` = the 7-digit base of the id (`1030003`), not a city. `SUBCODE` = the letter.
- The city is `DST_CITY`, a short code (`AL` for the sampled Alhambra-area precincts, `CC` for Carson's `1030003`).
  These codes are NOT the boundary layer's `ABBR` (`ALH`, `CAR`), so there is no ready code-to-name table.
  Plan: build the table from the SVC itself (an SVC precinct's LOCATION text and the city-contest block it belongs to),
  then check every name against the 88 boundary-layer city names, and report any code left unnamed.
- The layer is the 2026 precinct layer (last edited about Sept 2026). The 2024 PDF may use precinct ids that have since
  changed, so a 2024 dress rehearsal will show some unmatched ids. Report the share of ballots they cover.
- Distinct `CITY_EST` values exceed the 2,000-row page limit, so a full attribute download needs paging
  (`resultOffset`), about 17 pages for 33,219 polygons.

### Rehearsal run 1 (2024 precinct PDF, Nov 4, 2026): what worked and what was wrong

Worked: the parser read 369 contest blocks (0 errors). 21 countywide blocks had vote columns that equal the printed GRAND
TOTAL exactly. Carson came out with the same 26 precincts as its own mayor contest, and registration equal to the sum of
that contest's precinct rows (63,516; the printed total is 1 higher).

Wrong: the first version named each city code by majority vote over city-contest appearances. That produced
"89 of 89 codes named", but codes are not cities. Code `ZZ` is the unincorporated catch-all (SOUTH WHITTIER, RAMONA, EAST LOS
ANGELES) and was named Los Angeles because a few ZZ precincts appear in Los Angeles contests. Code `LM` (LOMITA) was named Los
Angeles for the same reason. Codes `CC`, `SU`, `SD`, `WF` had 0.5-0.7 purity. The sum check cannot see this: it passes
whatever the cities are, because it adds up every precinct. Those outputs were deleted from the repo.

Now (tools/svc_pipeline.py): each precinct gets its city from the strongest evidence, one precinct at a time:
direct (listed in that city's own contest) > pure code (at least 3 direct precincts, at least 98% agree) > place name equal to
a boundary city > otherwise "UNINCORPORATED OR UNKNOWN: <place>". The fallback rules are scored on precincts whose answer is
known, and the score is reported. Remaining weakness: a city with no contest this year can only be named by its code or its
place name, and a place name is not always the city (Sunland is in Los Angeles; Lomita-named precincts can be in Los Angeles).

### Rehearsal run 2: the second approach also failed, for a different reason (Nov 5, 2026)

Run 2 (direct contest evidence, then "pure" layer codes, then place names) reported 100% on its own score and put the
unincorporated communities (Ramona, South Whittier, Hacienda Heights, Castaic...) in Los Angeles. Cause: the score only tests
precincts that appear in some city's contest, and unincorporated precincts never do (selection bias). Also, the contest titled
"LOS ANGELES CITY ... MEASURE LL" lists 986 precincts while the other Los Angeles measures list 805, and its rows include
SOUTH GATE, LOMITA and unincorporated places, so it is wider than the city. A contest title does not describe its geography.
Lesson: a check that is blind to the failure it is meant to catch, and a source that agrees with itself, prove nothing.

Third approach (tools/precinct_geo.py, tools/svc_pipeline.py): the city of a precinct is decided by its SHAPE. The county
precinct layer's polygons are intersected with the county city-boundary polygons; the city covering most of the precinct wins,
and a precinct with under half of itself in any city is unincorporated. Contest evidence and place names are only cross-checks,
scored against the geometry over ALL geometry-known precincts, and their disagreements are listed. Precincts absent from the
2026 layer (about 1% in the 2024 file) fall back to the place name if it equals a city, else "UNASSIGNED: <place>".

Collector fixes found on the way (county API behaviour): it returns the same rows in a different order between requests, and
re-stamps its structure data every few minutes with nothing else changed, so byte comparison saved duplicate snapshots. The
collector now compares an order-independent form (`canonical_json`) and ignores the county's `TimeStamp` for the two
structure endpoints (`ignore_keys`). The history chart drops consecutive repeated tallies.

### Rehearsal run 3 (city from geometry): results and one bug (Nov 5, 2026)

Checks that do not depend on the geometry itself:
- Los Angeles: geometry put exactly 805 precincts in the city, the same number the five unambiguous Los Angeles measures list.
  Measure LL lists 986 (it is wider than the city), which the old approaches could not tell apart.
- Carson: 26 precincts, registration 63,516, the same as the sum of its own mayor contest's precinct rows.
- Place-name rule vs geometry: 2,103 of 2,110 precincts agree (99.7%).
- Contest listing vs geometry: 1,656 of 1,768 agree (93.7%). The disagreements are almost all the wide Measure LL listing
  unincorporated precincts (77) and parts of Gardena, Huntington Park, Bell and Beverly Hills (26) under "Los Angeles".
- 2,115 of 2,580 precincts (82%) had a shape match by exact id and 52 by 7-digit base; 17 were not in the 2026 layer and fell
  back to place names (8) or "UNASSIGNED" (9). That is a 2024-file vs 2026-layer effect; the 2026 file should match better.
- All 21 countywide contests: vote totals equal the printed GRAND TOTAL exactly.

Bug found by looking for the one boundary city with no precincts (Signal Hill, 87 of 88): the county's Long Beach polygon contains
all of Signal Hill with no hole cut out, so a Signal Hill precinct was covered completely by both cities and Long Beach won the tie.
Place name and the city's own contest both said Signal Hill. Fixed: when several cities each cover at least half a precinct,
the smallest wins (and the tool prints a note for every overlapping pair; Long Beach / Signal Hill is the only one). The
committed run-3 output in `data/rehearsal/` has Signal Hill missing and Long Beach 5 precincts too high until the next run.

Added: `city_reconciliation.csv`, which compares each city's own-contest registration with the registration of the precincts the
geometry assigned to it, so mismatches show up without manual inspection.

### Rehearsal run 4 (Signal Hill fixed): validated (Nov 5, 2026)

- All 88 boundary cities now have precincts (Signal Hill: 5 precincts that were in Long Beach).
- Place-name rule vs geometry: 2,108 of 2,110 (99.9%). Contest listing vs geometry: 1,661 of 1,768 (94.0%); the rest is the wide
  Measure LL listing unincorporated precincts and parts of Gardena, Huntington Park, Bell, Beverly Hills and Lomita under "Los Angeles".
- Registration reconciliation: of 63 cities with contests, 56 have a citywide contest to compare with, and all 56 match within 1%
  (45 exactly). The other 7 (Santa Clarita, Lomita, West Covina, Alhambra, Arcadia, La Mirada, Claremont) have only council-district
  contests in the 2024 file, so the reference is one district and the check cannot test them. They were off by 318-541%, which is
  what a single district against a whole city looks like. This is now reported as "not comparable", not as a failure.
- The 2026 file will test a different set of cities (59 cities have 2026 contests, 167 contests). Cities with no citywide contest
  stay unverified by reconciliation and rest on the geometry plus the place-name cross-check (99.9% agreement here).

What is NOT done: the 2026 SVC does not exist yet. Still to build once it does: matching SVC contest titles to API contests and SVC
vote columns to API choices (by matching the county totals, not by assuming column order), and showing city totals on the map.

### Countywide contests by city: built, waiting for the 2026 file (Nov 5, 2026)

Chain once the county publishes `4348_final_svc_precinct_public.pdf`: run the `svc-rehearsal` workflow with that URL (it writes
`data/rehearsal/4348_final_svc_precinct_public/`), then the `pages` workflow runs `python -m sitegen.city_totals`, which
  1. matches SVC contests to API contests by normalised title (no fuzzy matching; unmatched titles are listed in `city_totals_report.json`),
  2. matches SVC vote columns to API choices by the county totals, not by column order; equal non-zero totals are refused, and a
     contest whose totals differ (the live count moved past the certified file) is left out and reported, never shown mismatched,
  3. sums unincorporated places into one "Unincorporated areas" entry and only counts ballots that could not be placed.
The site then lists those contests under "Countywide contests, by city" in the map's colour menu; before that it says
"Not published by the county yet". Tested end to end on the real 2024 file's numbers with made-up choice names (kept out of the
repo): all 21 countywide contests joined, including ones whose API choice order was reversed.
Unverified until the real file exists: that 2026 contest titles match the API's wording, and the file layout (candidate-name
columns, multi-seat or retention contests) is the same as 2024. The pipeline stops with an error rather than guess on a new layout.

### Automatic start of the 2026 pipeline (Nov 5, 2026)

`fetch.yml` already probes `svc_2026_precinct_pdf` every run. `tools/svc_auto.py` reads that probe; when it is HTTP 200, a PDF, and
at least 1 MB, it starts `svc-rehearsal` for that URL (`gh workflow run`, `actions: write`), once per version of the file
(size + Last-Modified). A changed file is processed again, because the county may publish an early file and replace it. A run
that produced no output is retried at most 3 times, an hour apart, then waits for the file to change. State is committed in
`data/svc_auto/state.json`. `svc-rehearsal` finishes by triggering `pages`, which rebuilds the city totals.
The two svc workflows use their own concurrency group, because a shared group keeps only one pending run and a later fetch run
could cancel the dispatched one. Every commit step retries `pull --rebase && push`.
Known risks: the file name is a guess (`4348_final_svc_precinct_public.pdf`). The county's names vary (`4306_final_svc_precinct_public`,
`4291_svc_precinct_zbc`, `4324_final_svc_district_v3`), so if the real 2026 name differs the probe never fires and the pipeline is
started by hand with the real URL. `city_totals` finds the output folder by `<election id>_*precinct*`, preferring a whole-word "final".
Self-test: run fetch manually with "test_dispatch" ticked; it starts svc-rehearsal for the published 2024 file.

### Daily search for the real 2026 file name (Nov 5, 2026)

`svc-discover.yml` runs once a day (and on demand). `tools/svc_discover.py` (1) reads a few county pages (seeds in
`config/sources.json` under `svc_discovery`; county hosts only, at most 40 pages, depth 2) and collects links to
`/docs/rrcc/svc/` PDFs, and (2) HEAD-probes those links plus 60 systematic names built from the real names seen so far
(`<id>_[final|semifinal|semi_final]_svc_<precinct|countywide|district>[_public|_v2|_v3|_v4]`; a test checks the generator reproduces every real
name we have seen). It starts `svc-rehearsal` only for a PRECINCT report of THIS election that is HTTP 200, a PDF, at least 1 MB,
and not a "zbc" file (the zero-ballot report made before the election), once per version and with the retry limits of
`tools/svc_auto.py`. The guessed name that `fetch.yml` already watches is left to `fetch.yml` so one file is never started twice.
Everything it finds is recorded in `data/svc_auto/discovered.json`, including countywide and district reports.
Limits: it can only find names inside the guessed pattern space or linked from a county page it can reach; whether any county
page links to these files is unknown (no page I have seen does). If neither method finds the file, start `svc-rehearsal` by hand
with the real URL.

### The real 2026 files are already published (found by the daily discovery, Nov 5, 2026)

The county published its precinct-level files at 00:03 UTC on Nov 5 (4:03 PM Pacific, Nov 4), for the unofficial count, under names
my guess did not match. Real names: `4348_svc_precinct_public.pdf` (97 MB, 9,805 pages, the by-contest SVC), `4348_precinct_public.pdf` (44 MB, a
different report: the pipeline stopped with "layout not known"), `4348_svc_countywide.pdf`, `4348_svc_districts.pdf`, `4348_city_council.pdf`,
`4348_community.pdf`. The county's own pages list 205 SVC links across elections, so new versions will be found. Earlier elections show
later versions under new names (`4338_..._v3`, `_v4`; `4324_final_svc_precinct_public_v2`; `4300_svc_precinct_public-v2`).
The file is labelled "SEMIFINAL OFFICIAL CANVASS V2": a preliminary canvass, not the final one.

Pipeline on the real 2026 file: 409 contest blocks (the API has 409 contests), 0 parse errors, 50 countywide blocks whose vote totals equal the printed
GRAND TOTAL exactly, 88 of 88 boundary cities with precincts, registration within 1% of each city's own contests for 47 of 49 comparable cities (all 49
within 5%), place-name rule vs geometry 99.6%.

What did not join, and why (all found by running it, none by assumption):
- The file is cut from a tally slightly earlier than the earliest one we saved (our collector began saving at 10:54 AM Pacific). Real example, Sheriff:
  file 1,330,305 / 610,722 vs our 3:11:55 AM tally 1,330,743 / 611,041 (0.03-0.05% apart). So exact matching of column totals finds nothing.
  Now: totals are matched to the nearest saved tally within 0.5% (or 3 votes), every value needs exactly one counterpart, and contests whose values are
  close enough to be swapped are refused. The gap is stored per contest and shown on the site.
- 2026 header layouts differ from 2024: "Voter Nominated :" alone on a line with the title on the next; a "Los Angeles County Results Only" prefix on
  statewide contests; retention questions wrapping over several lines. The parser now keeps the whole header text and the API's contest title is
  found in it as a whole-word phrase (retention contests: the part before " - " and the name). `STATE MEASURE 1` does not match `STATE MEASURE 10`.
- `4348_precinct_public.pdf` is not the by-contest report. Automatic starts now require "svc" and "precinct" in the name.

### A more reliable collector (Nov 5, 2026)

Problem: GitHub's scheduler is best-effort. The 15-minute fetch ran about twice in 12 hours, so county tallies posted in between were never saved
(the first SVC file was cut from a tally we never saved), and later county files can only be joined to the live feed if a nearby tally was saved.
Changes:
- `poll.yml` does its own timing: one collection cycle every 5 minutes for about 5 h 40 min, then it starts the next poller (`handover`); a scheduled
  backstop (`12,42 * * * *`) starts one if none is running. It stops on 2026-12-20 (UTC). Free for a public repository; about 700 runner minutes a day if the
  repository were private. Stop it earlier by disabling the workflow and cancelling the running job.
- `fetch.yml` remains as a backstop twice an hour at off-peak minutes (`7,37 * * * *`).
- Both run `tools/fetch_cycle.sh`: reset to origin, fetch, parse, decide whether the SVC file appeared, commit and push ONLY when something other than the
  attempt log changed (otherwise there would be a commit every few minutes), rebuild the site after a new county tally, start the SVC pipeline when the file
  appears. Tested against a local bare repository with a fake `gh`, including a mutation check: removing the reset or the log-only rule makes tests fail.
- The collector retries a request after a dropped connection, a timeout, HTTP 429 or 5xx (three attempts); a 4xx answer is never retried, because some sources
  are probed on purpose for files that do not exist yet. A missing local file is not retried either.
- The site shows when the page was built.
Known gaps: nothing alerts if collection stalls. A stall shows as the last data commit getting old, or as failed poll/fetch runs. The attempt log is only committed
together with a real change, so "nothing changed" cycles leave no trace in the repository.
