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
export function extremes(t, n = 5, filter, min = MIN_RANK) {
  const list = [...t.rows.entries()].filter(([, x]) => x.rate !== null && x.reg >= min && (!filter || filter(x))).map(([id, x]) => ({ id, ...x }));
  list.sort((a, b) => b.rate - a.rate);
  return { highest: list.slice(0, n), lowest: list.slice(-n).reverse(), eligible: list.length };
}

// ---- vote by mail versus in person -------------------------------------------------------------------------------------------------
// The county's file splits every precinct row into vote-by-mail and total; in person = total - vote by mail.
// rowAll = [registration, ballots, votes...] and rowVbm = [vbm ballots, vbm votes...], votes in the same choice order.
// Returns the vote lists and ballot counts for all ballots, vote-by-mail ballots and in-person ballots (never negative).
export function methodSplit(rowAll, rowVbm) {
  const all = rowAll.slice(2), vbm = rowVbm.slice(1);
  const ip = all.map((v, i) => Math.max(0, v - (vbm[i] || 0)));
  return { all, vbm, ip, ballots: { all: rowAll[1], vbm: rowVbm[0], ip: Math.max(0, rowAll[1] - rowVbm[0]) } };
}
// Share of the votes in a list that went to choice i, or null when the list is empty.
export const shareOf = (votes, i) => { const t = votes.reduce((a, b) => a + b, 0); return t ? votes[i] / t : null; };
// How much better choice i did in person than by mail, as a share difference (0.10 = 10 points); null if either group has no votes.
export function inPersonMinusMail(split, i) {
  const a = shareOf(split.ip, i), b = shareOf(split.vbm, i);
  return a === null || b === null ? null : a - b;
}

// Share of ballots cast by mail in each precinct. Ballots and the mail part come from the same countywide contest: the one with the most
// ballots in that precinct (as in turnoutByPrecinct). method: {precinct id: {contest id: [vbm ballots, vbm votes...]}}.
export function vbmShareByPrecinct(prec, method, contestIds) {
  const ids = new Set(contestIds.map(String));
  const rows = new Map();
  let vbm = 0, ballots = 0;
  for (const [pid, p] of Object.entries(prec.votes)) {
    let best = null;
    for (const [cid, row] of Object.entries(p.v)) if (ids.has(cid) && method[pid] && method[pid][cid] && (!best || row[1] > best.ballots)) best = { ballots: row[1], vbm: method[pid][cid][0] };
    if (!best) continue;
    rows.set(pid, { reg: best.ballots, ballots: best.ballots, vbm: best.vbm, rate: best.ballots > 0 ? best.vbm / best.ballots : null, city: p.city });
    vbm += best.vbm; ballots += best.ballots;
  }
  const rates = [...rows.values()].filter((x) => x.rate !== null && x.ballots >= MIN_SCALE).map((x) => x.rate).sort((a, b) => a - b);
  const q = (p) => (rates.length ? rates[Math.min(rates.length - 1, Math.floor(p * (rates.length - 1)))] : 0);
  return { rows, reg: ballots, ballots, vbm, lo: q(0.05), hi: q(0.95) };
}
// Vote-by-mail share of a group of precincts (a city): total mail ballots / total ballots.
export function vbmOf(t, filter) {
  let vbm = 0, ballots = 0, n = 0;
  for (const x of t.rows.values()) if (!filter || filter(x)) { vbm += x.vbm; ballots += x.ballots; n++; }
  return { vbm, ballots, n, rate: ballots ? vbm / ballots : null };
}
