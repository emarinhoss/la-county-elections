// Analyses computed in the browser from the precinct file. Pure functions: easy to test and to explain.

// Turnout per precinct = ballots cast / registered voters.
// "Ballots cast" in a precinct is the most ballots any countywide contest recorded there (every voter gets those contests, and in
// the 2026 file this sums to within 0.01% of the county's own ballots-counted at the same tally; one contest alone, such as Governor,
// comes out slightly low in about a third of precincts). Registration is the same in every countywide contest.
// prec: {votes: {precinct id: {city, v: {contest id: [registration, ballots, votes...]}}}}; contestIds: ids of the countywide contests.
export function turnoutByPrecinct(prec, contestIds) {
  const ids = new Set(contestIds.map(String));
  const rows = new Map();
  let reg = 0, ballots = 0;
  for (const [pid, p] of Object.entries(prec.votes)) {
    let r = null, b = 0;
    for (const [cid, row] of Object.entries(p.v)) if (ids.has(cid)) { r = row[0]; b = Math.max(b, row[1]); }
    if (r === null) continue;
    rows.set(pid, { reg: r, ballots: b, rate: r > 0 ? b / r : null, city: p.city });
    reg += r; ballots += b;
  }
  // The colour scale runs from the 5th to the 95th percentile of precincts with at least MIN_SCALE registered voters, so a few tiny
  // precincts with extreme rates do not wash out the map.
  const rates = [...rows.values()].filter((x) => x.rate !== null && x.reg >= MIN_SCALE).map((x) => x.rate).sort((a, b) => a - b);
  const q = (p) => (rates.length ? rates[Math.min(rates.length - 1, Math.floor(p * (rates.length - 1)))] : 0);
  return { rows, reg, ballots, lo: q(0.05), hi: q(0.95) };
}
export const MIN_SCALE = 200;     // registered voters needed for a precinct to count towards the colour scale
export const MIN_RANK = 500;      // registered voters needed to appear in the highest/lowest lists (a handful of voters cannot top a list)

// 0..1 position of a rate on the colour scale.
export const scale = (rate, lo, hi) => (hi > lo ? Math.max(0, Math.min(1, (rate - lo) / (hi - lo))) : 0.5);

// Turnout of a group of precincts (a city): total ballots / total registered.
export function turnoutOf(t, filter) {
  let reg = 0, ballots = 0, n = 0;
  for (const x of t.rows.values()) if (!filter || filter(x)) { reg += x.reg; ballots += x.ballots; n++; }
  return { reg, ballots, n, rate: reg ? ballots / reg : null };
}

// The n highest and n lowest precincts among those with at least MIN_RANK registered voters.
export function extremes(t, n = 5, filter) {
  const list = [...t.rows.entries()].filter(([, x]) => x.rate !== null && x.reg >= MIN_RANK && (!filter || filter(x))).map(([id, x]) => ({ id, ...x }));
  list.sort((a, b) => b.rate - a.rate);
  return { highest: list.slice(0, n), lowest: list.slice(-n).reverse(), eligible: list.length };
}
