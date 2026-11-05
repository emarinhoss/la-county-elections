# Plan: precinct-level results on the map

Problem (found Nov 5, 2026): the county's precinct Statement of Votes Cast (SVC) reports **consolidated** election precincts
(2,187 ids in the 2026 file; the election data says 2,853 exist), while the shape layer we joined to is the county's
**established** precincts (33,219 polygons, 11,816 base numbers). An exact-id join draws one small piece of each consolidated
precinct, so the map looked mostly empty. The votes are right; the shapes are the wrong layer. Nothing is published until fixed
(`sitegen/precincts.PUBLISH = False`).

## What the research found (Nov 5, web search; pages not opened from the sandbox, which cannot reach these hosts)

| Source | What it is | Use |
|---|---|---|
| LA County GIS hub, **Registrar Recorder Election Precincts** | "The RRCC's GIS Section consolidates Established Precincts based on an election's shared active districts." 2,853 records, fields for consolidated precinct id, vote-by-mail flag, ballot group, serial number, voter counts. Sample ids `6220036A`, `1040049D` = the SVC id format. Updated before each RRCC election (data update Aug 31, 2026). | **Primary.** This is the shape layer the SVC precincts should join to. |
| LA County GIS hub, Established Precincts (what we use today) | "For maintaining voter distributions across the County and not for reporting voting results." | Keep only for the precinct→city assignment, or replace with the election layer. |
| UC Berkeley **Statewide Database** (statewidedatabase.org) | Per-election precinct shapefiles (SRPREC, SVPREC) and RG→RR→SR→SV conversion files for every county, from each county's SOV. | **Fallback**, but it appears months after an election; the 2026 primary is the newest. |
| California Secretary of State, Statement of Vote | County and district totals, PDF/XLSX. No precinct level. SOS points to the Statewide Database for precincts. | Not useful for shapes. |
| lavote.gov election results file downloads | JSON/ETS results files, 95-byte fixed records. | Not checked for precinct ids; low priority. |

Sources: hub pages for the [election precincts layer](https://egis-lacounty.hub.arcgis.com/datasets/lacounty::registrar-recorder-election-precincts-/about)
and [established precincts](https://www.arcgis.com/home/item.html?id=7844563964514c1e87df3e250214306a); the
[Statewide Database 2026 primary geography page](https://www.statewidedatabase.org/d20/p26_geo_conv.html) and its
[precinct data notes](https://statewidedatabase.org/info/metadata/precinct_data.html); the SOS
[2024 Statement of Vote](https://www.sos.ca.gov/elections/prior-elections/statewide-election-results/general-election-nov-5-2024/statement-vote);
[lavote.gov results downloads](https://www.lavote.gov/home/voting-elections/current-elections/election-results-file-downloads).

## Tasks

Each task has an acceptance test. A task that fails its test is reported, not worked around.

1. **Find the election-precincts service** (probes added to `config/sources.json`: `rrcc_services_directory`,
   `election_precincts_layer_guess`, `election_precincts_sample_guess`). Run the fetch workflow.
   Accept: the services directory names a service for election/consolidated precincts; the layer metadata lists its fields;
   25 sample rows show the consolidated id field. Record the exact service URL and field names in `docs/specs/00_spec.md`.
2. **Check the id match before any shapes are drawn.** Download all ~2,853 attribute rows (no geometry) in the fetch workflow.
   Accept: ≥ 99% of the 2,187 SVC ids appear in the layer; every unmatched id is listed with its ballots. Also report how many
   layer ids have no SVC row (expected: precincts with no voters, or vote-by-mail-only precincts, if the layer flags them).
3. **Download the consolidated shapes** in `svc-rehearsal.yml` (new tool `tools/election_precinct_shapes.py`, paged, count-checked,
   like `tools/precinct_geo.py`), save `data/rehearsal/<name>/precinct_shapes.geojson` from the election layer, keyed by the
   consolidated id. Accept: one polygon per SVC id that matched in task 2; file ≤ 5 MB after 5-decimal rounding; the workflow
   summary prints matched/unmatched counts.
4. **Re-derive precinct → city from the consolidated shapes** (same rule as `tools/precinct_geo.py`: smallest city covering ≥ 50%),
   and compare with the current assignment, which used one established-precinct piece per consolidated precinct.
   Accept: a table of precincts whose city changed, with ballots; the city totals are rebuilt and `city_totals_report.json` shows
   every contest still within tolerance of the county tally. If more than 1% of ballots change city, stop and report.
5. **Turn the layer on** (`PUBLISH = True`), rebuild locally, test in the headless browser on the real shapes.
   Accept: the map is covered (no large gray holes inside the county apart from precincts with no voters), ≤ 2 s to draw,
   tooltip and click panel work, 11 earlier UI checks still pass, 89+ Python tests pass.
6. **Deploy and verify** on GitHub Pages. Accept: the Precincts button appears for a countywide contest; a known precinct
   (e.g. a Carson one) shows the same numbers as the PDF row.
7. **Fallback if task 1 or 2 fails**: (a) ask the county GIS contact in the layer metadata for the consolidation list;
   (b) wait for the Statewide Database's 2026 general files; (c) meanwhile show a precinct results *table* (no shapes).

## Rules that apply

- No guessed consolidation. Shapes come only from a county layer whose ids equal the SVC ids.
- Every number on the site traces to a run recorded in this repo; the matched/unmatched counts go in the workflow summary
  and the spec.
- The by-precinct numbers carry the same caveat as by-city: they are frozen at the SVC's tally, which can trail the live count.
