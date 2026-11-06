// Loads the data files once and builds the lookups every view uses.
import { getJSON, titleCase } from "./util.js";

export const S = { city: null, county: null, totals: null, shapes: null, cwList: [], cwById: {}, cityByKey: {}, countyList: [], byId: {}, cityContests: [] };
let historyPromise = null;
export const getHistory = () => (historyPromise ||= getJSON("data/history.json"));
// Precinct votes and shapes are large, so they load only when someone turns the precinct layer on. Resolves to null if the
// county's precinct file has not been processed yet.
let precinctPromise = null;
export const getPrecincts = () => (precinctPromise ||= Promise.all([getJSON("data/precincts.json"), getJSON("data/precincts.geojson")])
  .then(([votes, shapes]) => ({ votes: votes.p, names: votes.names || {}, shapes })).catch(() => null));

export async function load() {
  // city_contests.json is required; everything else may be missing and the views say so.
  S.city = await getJSON("data/city_contests.json");
  const [county, totals] = await Promise.all([getJSON("data/county_contests.json").catch(() => null), getJSON("data/city_totals.json").catch(() => null)]);
  S.county = county;
  S.totals = totals && totals.available ? totals : null;
  S.totalsReason = totals && !totals.available ? totals.reason : null;

  for (const city of S.city.cities) {
    S.cityByKey[city.key] = city;
    for (const c of city.contests) { c.city = city.name; c.cityKey = city.key; S.byId["c" + c.id] = c; S.cityContests.push(c); }
  }
  if (county) for (const g of county.groups) for (const c of g.contests) { c.group = g.name; S.countyList.push(c); S.byId["k" + c.id] = c; }
  if (S.totals) for (const cw of S.totals.contests) { cw.label = titleCase(cw.label); S.cwList.push(cw); S.cwById[cw.id] = cw; }
  S.shapes = await getJSON("data/city_boundaries.geojson").catch(() => null);
}

export const cityName = (key) => (S.cityByKey[key] && S.cityByKey[key].name) ||
  (S.totals && S.totals.contests.map((c) => c.cities[key]).find(Boolean) || {}).name || null;
export const countyContest = (id) => S.byId["k" + id] || null;

// The one-sentence title of a measure (the county's own headline or first sentence). Countywide-by-city contests carry no text of their
// own, so they borrow it from the county contest with the same id.
export const measureTitleOf = (c) => c.measure_title || (S.byId["k" + c.id] || {}).measure_title || null;
