// Draws the map and the results panel from two files:
//   data/city_contests.json       results per city (always present)
//   data/city_boundaries.geojson  city shapes (may be missing; the city list still works)
// Text is added with textContent (never innerHTML) so county text can never inject markup.

const BLUE = "#1f6fb2", ORANGE = "#d9822b", GREY = "#c9ced6";
let map, layer, cityView, data, cityTotals = null, selectedKey = null, colorContestId = "";
const byKey = {};

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text !== undefined) e.textContent = text;
  return e;
}
const pct = (x) => (x === null ? "–" : (x * 100).toFixed(1) + "%");
const num = (x) => (x === null || x === undefined ? "–" : x.toLocaleString("en-US"));

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

// ---- colors -------------------------------------------------------------
// Default: cities with contests are blue, others grey.
// A selected measure: blue when YES leads, orange when NO leads, shade shows how far from 50%.
// A selected candidate contest: shade of blue shows the leader's share.
function shade(hex, strength) { // strength 0..1 blends the color toward white
  const n = parseInt(hex.slice(1), 16), mix = (c) => Math.round(255 - (255 - c) * strength);
  return `rgb(${mix(n >> 16)},${mix((n >> 8) & 255)},${mix(n & 255)})`;
}
function contestColor(contest) {
  const top = [...contest.choices].sort((a, b) => b.votes - a.votes)[0];
  if (!top || top.share === null) return GREY;
  if (contest.kind === "measure") {
    const yes = contest.choices.find((c) => c.name.toUpperCase() === "YES");
    if (!yes || yes.share === null) return GREY;
    const d = Math.min(Math.abs(yes.share - 0.5) / 0.3, 1);
    return shade(yes.share >= 0.5 ? BLUE : ORANGE, 0.35 + 0.65 * d);
  }
  return shade(BLUE, 0.35 + 0.65 * Math.min(top.share, 1));
}
// ---- countywide contests by city (data/city_totals.json, from the county's precinct-level results) -------------------
// kind "measure": blue where YES leads, orange where NO leads. Two candidates: blue where the county-wide leader is ahead
// in that city, orange where the other is. More than two: shade of blue shows the county leader's share.
function cwContest() {
  if (!colorContestId.startsWith("cw:") || !cityTotals || !cityTotals.available) return null;
  return cityTotals.contests.find((c) => "cw:" + c.id === colorContestId) || null;
}
function cwLeader(cw) {
  return cw.choices.reduce((best, c, i) => (c.county_votes > cw.choices[best].county_votes ? i : best), 0);
}
function cwColor(cw, entry) {
  const total = entry.votes.reduce((s, v) => s + v, 0);
  if (!total) return GREY;
  const focus = cw.kind === "measure" ? Math.max(0, cw.choices.findIndex((c) => c.name.toUpperCase() === "YES")) : cwLeader(cw);
  const share = entry.votes[focus] / total;
  if (cw.kind === "measure" || cw.choices.length === 2) {
    const d = Math.min(Math.abs(share - 0.5) / 0.3, 1);
    return shade(share >= 0.5 ? BLUE : ORANGE, 0.35 + 0.65 * d);
  }
  return shade(BLUE, 0.35 + 0.65 * Math.min(share, 1));
}
function featureColor(props) {
  const cw = cwContest();
  if (cw) { const e = cw.cities[props.key]; return e ? cwColor(cw, e) : GREY; }
  const city = byKey[props.key];
  if (!city) return GREY;
  if (colorContestId) {
    const c = city.contests.find((x) => String(x.id) === colorContestId);
    return c ? contestColor(c) : GREY;
  }
  return shade(BLUE, 0.35 + 0.65 * Math.min(city.contests.length / 6, 1));
}
function style(feature) {
  const p = feature.properties, picked = p.key === selectedKey, cw = cwContest();
  const filled = cw ? !!cw.cities[p.key] : p.has_contests;
  return { fillColor: featureColor(p), fillOpacity: filled ? 0.9 : 0.35,
           color: picked ? "#000" : "#6b7480", weight: picked ? 2.5 : 0.7 };
}

function drawLegend() {
  const box = document.getElementById("legend");
  box.replaceChildren();
  const add = (color, text) => {
    const row = el("div");
    const s = el("span", "swatch"); s.style.background = color;
    row.append(s, document.createTextNode(text));
    box.append(row);
  };
  if (!colorContestId) { add(BLUE, "City with contests (darker = more)"); add(GREY, "No contests on this ballot"); return; }
  const cw = cwContest();
  if (cw) {
    if (cw.kind === "measure") { add(BLUE, "YES leads"); add(ORANGE, "NO leads"); }
    else if (cw.choices.length === 2) { const l = cwLeader(cw); add(BLUE, cw.choices[l].name + " ahead"); add(ORANGE, cw.choices[1 - l].name + " ahead"); }
    else add(BLUE, cw.choices[cwLeader(cw)].name + "'s share (darker = larger)");
    add(GREY, "No precinct data");
    return;
  }
  const c = Object.values(byKey).flatMap((x) => x.contests).find((x) => String(x.id) === colorContestId);
  if (c && c.kind === "measure") { add(BLUE, "YES leads"); add(ORANGE, "NO leads"); add(GREY, "Other cities"); }
  else { add(BLUE, "Leader's share (darker = larger)"); add(GREY, "Other cities"); }
}


// ---- count over time ----------------------------------------------------------
// data/history.json has one entry per saved county tally. History starts when our collector started saving.
// Colors are a colorblind-safe set (Okabe-Ito); the legend and table also carry the names and numbers.
const LINE_COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"];
let historyPromise = null;
const getHistory = () => (historyPromise ||= getJSON("data/history.json"));
const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs) {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
  return e;
}
function fmtTime(t) { // county times have no time zone: show the same wall clock the county printed
  const d = new Date(t.county_iso);
  return isNaN(d) ? t.county_time : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

// series: [{name, values:[number|null per tally]}]; format turns a value into text for the axis
function lineChart(series, times, format, label) {
  const W = 560, H = 220, L = 74, R = 14, T = 10, B = 30;
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", "aria-label": label });
  const all = series.flatMap((s) => s.values.filter((v) => v !== null));
  if (all.length === 0) return root;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi - lo < 1e-9) { lo -= Math.abs(lo) * 0.05 + 0.01; hi += Math.abs(hi) * 0.05 + 0.01; }
  const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
  const stamps = times.map((t) => Date.parse(t.county_iso));
  const useTime = stamps.every((s) => !isNaN(s)) && stamps[stamps.length - 1] > stamps[0];
  const xs = times.map((_, i) => {
    const f = times.length === 1 ? 0.5 : useTime ? (stamps[i] - stamps[0]) / (stamps[stamps.length - 1] - stamps[0]) : i / (times.length - 1);
    return L + f * (W - L - R);
  });
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  for (let k = 0; k <= 3; k++) { // horizontal grid + y labels
    const v = lo + ((hi - lo) * k) / 3, yy = y(v);
    root.append(svg("line", { x1: L, x2: W - R, y1: yy, y2: yy, class: "grid" }));
    const t = svg("text", { x: L - 6, y: yy + 4, "text-anchor": "end" }); t.textContent = format(v); root.append(t);
  }
  [0, times.length - 1].forEach((i, n) => { // first and last tally time on the x axis
    if (n === 1 && i === 0) return;
    const t = svg("text", { x: xs[i], y: H - 8, "text-anchor": times.length === 1 ? "middle" : n === 0 ? "start" : "end" });
    t.textContent = fmtTime(times[i]); root.append(t);
  });
  series.forEach((s, k) => {
    const color = LINE_COLORS[k % LINE_COLORS.length];
    const pts = s.values.map((v, i) => (v === null ? null : [xs[i], y(v)])).filter(Boolean);
    if (pts.length > 1) root.append(svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: color, "stroke-width": 2 }));
    pts.forEach((p) => root.append(svg("circle", { cx: p[0], cy: p[1], r: 3.5, fill: color })));
  });
  return root;
}

function historyTable(rows, header) {
  const t = el("table", "hist");
  const head = el("tr"); header.forEach((h) => head.append(el("th", null, h))); t.append(head);
  rows.forEach((r) => { const tr = el("tr"); r.forEach((c) => tr.append(el("td", null, c))); t.append(tr); });
  return t;
}
function legend(series) {
  const box = el("div", "hist-legend");
  series.forEach((s, k) => {
    const item = el("span"); const sw = el("span", "swatch"); sw.style.background = LINE_COLORS[k % LINE_COLORS.length];
    item.append(sw, document.createTextNode(s.name)); box.append(item);
  });
  return box;
}
function oneTallyNote(times) {
  return el("p", "muted", `Only ${times.length === 1 ? "one tally has" : times.length + " tallies have"} been recorded so far ` +
    `(county time ${fmtTime(times[times.length - 1])}). Earlier election-night tallies were published before this collector started saving. ` +
    (times.length === 1 ? "The chart fills in as the county posts updates." : ""));
}

// Share of votes per choice, over the recorded tallies (top 6 choices by latest votes).
function drawContestHistory(box, contest, h) {
  const hc = h.contests[String(contest.id)];
  if (!hc) { box.append(el("p", "muted", "No history for this contest.")); return; }
  const n = h.times.length;
  const top = [...hc.choices].sort((a, b) => (b.votes[n - 1] || 0) - (a.votes[n - 1] || 0)).slice(0, 6);
  const totals = h.times.map((_, i) => hc.choices.reduce((sum, c) => sum + (c.votes[i] || 0), 0));
  const series = top.map((c) => ({ name: c.name, values: c.votes.map((v, i) => (v === null || totals[i] === 0 ? null : v / totals[i])) }));
  box.append(lineChart(series, h.times, (v) => (v * 100).toFixed(1) + "%",
    `Share of votes over ${n} tally${n === 1 ? "" : "s"}: ` + top.map((c, k) => `${c.name} ${pct(series[k].values[n - 1])}`).join(", ")));
  box.append(legend(series));
  if (n < 3) box.append(oneTallyNote(h.times));
  const last = h.times.map((t, i) => [fmtTime(t), num(hc.ballots[i]), ...top.map((c) => num(c.votes[i]))]).slice(-10).reverse();
  box.append(historyTable(last, ["Tally (county time)", "Ballots", ...top.map((c) => c.name)]));
}
function lazyHistory(summaryText, draw) {
  const d = el("details", "history"); d.append(el("summary", null, summaryText));
  const body = el("div"); d.append(body);
  d.addEventListener("toggle", () => {
    if (!d.open || d.dataset.done) return;
    d.dataset.done = "1";
    getHistory().then((h) => draw(body, h)).catch((e) => body.append(el("p", "muted", "History could not be loaded: " + e.message)));
  });
  return d;
}

// ---- panel ----------------------------------------------------------------
function renderContest(c) {
  const box = el("div", "contest");
  box.append(el("h3", null, c.label));
  const bits = [c.kind === "measure" ? "Measure" : "Candidate contest"];
  if (c.vote_for > 1) bits.push("vote for up to " + c.vote_for);
  if (c.kind === "measure" && c.pass_rate) bits.push("passes with: " + c.pass_rate);
  bits.push(num(c.ballots_cast) + " ballots counted");
  box.append(el("div", "meta", bits.join(" · ")));
  const topVotes = Math.max(...c.choices.map((x) => x.votes));
  for (const ch of [...c.choices].sort((a, b) => b.votes - a.votes)) {
    const row = el("div", "choice" + (ch.votes === topVotes && topVotes > 0 ? " top" : ""));
    const name = ch.party && ch.party !== "Non Partisan" ? `${ch.name} (${ch.party})` : ch.name;
    row.append(el("span", null, name), el("span", null, `${num(ch.votes)} · ${pct(ch.share)}`));
    const bar = el("div", "bar"), fill = el("span");
    fill.style.width = (ch.share === null ? 0 : ch.share * 100) + "%";
    bar.append(fill); row.append(bar); box.append(row);
  }
  if (c.measure_text) {
    const d = el("details"); d.append(el("summary", null, "Measure text"), el("p", null, c.measure_text)); box.append(d);
  }
  box.append(lazyHistory("Count over time", (body, h) => drawContestHistory(body, c, h)));
  return box;
}
// The selected countywide contest's result in one area, with how sure we are about where its ballots belong.
function renderCwResult(cw, key) {
  const box = el("div", "contest cw");
  box.append(el("h3", null, cw.label + " (countywide contest, this area)"));
  const e = cw.cities[key];
  if (!e) { box.append(el("div", "meta", "No precinct-level data for this area.")); return box; }
  const bits = [num(e.ballots) + " ballots", num(e.registration) + " registered", "from precinct results"];
  if (e.fallback_ballots > 0) bits.push(pct(e.fallback_ballots / e.ballots) + " of these ballots placed by place name (no precinct shape found)");
  box.append(el("div", "meta", bits.join(" · ")));
  const total = e.votes.reduce((s, v) => s + v, 0), top = Math.max(...e.votes);
  cw.choices.map((c, i) => ({ c, v: e.votes[i] })).sort((x, y) => y.v - x.v).forEach(({ c, v }) => {
    const row = el("div", "choice" + (v === top && top > 0 ? " top" : ""));
    const name = c.party && c.party !== "Non Partisan" ? `${c.name} (${c.party})` : c.name;
    row.append(el("span", null, name), el("span", null, `${num(v)} · ${pct(total ? v / total : null)}`));
    const bar = el("div", "bar"), fill = el("span");
    fill.style.width = (total ? (v / total) * 100 : 0) + "%";
    bar.append(fill); row.append(bar); box.append(row);
  });
  return box;
}
function showCity(key) {
  selectedKey = key;
  const sel = document.getElementById("city-select");
  sel.value = [...sel.options].some((o) => o.value === key) ? key : "";
  const panel = document.getElementById("contests");
  panel.replaceChildren();
  const city = byKey[key], cw = cwContest();
  const cwName = cw && cw.cities[key] ? cw.cities[key].name : null;
  if (!city && !cwName) {
    panel.append(el("p", "muted", "Choose a city on the map or from the list."));
    if (cw) panel.append(el("p", "muted", "Countywide results by city come from the county's precinct-level results: each precinct is placed in the city whose boundary " +
      "contains it. " + num(cw.unassigned_ballots) + " ballots in this contest could not be placed in any city or unincorporated area."));
  } else {
    panel.append(el("h2", null, city ? city.name : cwName));
    if (cw) panel.append(renderCwResult(cw, key));
    if (city) city.contests.forEach((c) => panel.append(renderContest(c)));
  }
  if (layer) layer.setStyle(style);
}

// ---- setup ----------------------------------------------------------------
function fillSelects() {
  const citySel = document.getElementById("city-select");
  citySel.append(new Option("Select a city…", ""));
  data.cities.forEach((c) => citySel.append(new Option(`${c.name} (${c.contests.length})`, c.key)));
  citySel.addEventListener("change", () => showCity(citySel.value));

  const cSel = document.getElementById("contest-select");
  cSel.append(new Option("Number of contests", ""));
  for (const city of data.cities) {
    const group = document.createElement("optgroup");
    group.label = city.name;
    city.contests.forEach((c) => group.append(new Option(c.label, String(c.id))));
    cSel.append(group);
  }
  const cwGroup = document.createElement("optgroup");
  cwGroup.label = "Countywide contests, by city (from precinct results)";
  if (cityTotals && cityTotals.available) cityTotals.contests.forEach((c) => cwGroup.append(new Option(c.label, "cw:" + c.id)));
  else cwGroup.append(Object.assign(new Option("Not published by the county yet", ""), { disabled: true }));
  cSel.append(cwGroup);
  if (cityTotals && cityTotals.available) { // cities with no contest of their own can still have countywide results
    const known = new Set(data.cities.map((c) => c.key)), extra = {};
    cityTotals.contests.forEach((c) => Object.entries(c.cities).forEach(([k, v]) => { if (!known.has(k)) extra[k] = v.name; }));
    Object.entries(extra).sort((x, y) => x[1].localeCompare(y[1])).forEach(([k, name]) => citySel.append(new Option(name + " (countywide only)", k)));
  }
  cSel.addEventListener("change", () => {
    colorContestId = cSel.value;
    const owner = data.cities.find((city) => city.contests.some((c) => String(c.id) === colorContestId));
    if (owner) showCity(owner.key); else showCity(selectedKey);
    drawLegend();
  });
}

// ---- county / state / district view -------------------------------------
let countyData = null;
function renderCounty() {
  const group = countyData.groups.find((g) => g.name === document.getElementById("group-select").value);
  const filter = document.getElementById("county-filter").value.trim().toLowerCase();
  const box = document.getElementById("county-contests");
  box.replaceChildren();
  const shown = group.contests.filter((c) => c.label.toLowerCase().includes(filter));
  shown.forEach((c) => box.append(renderContest(c)));
  document.getElementById("county-note").textContent =
    `${shown.length} of ${group.contests.length} contests. Numbers are the Los Angeles County totals; ` +
    "a contest that spans several counties shows only its Los Angeles County part.";
}
function setupCounty() {
  const t = countyData.totals;
  const totals = document.getElementById("totals");
  const stat = (label, value) => { const d = el("div"); d.append(el("div", "big", value), el("div", "muted", label)); totals.append(d); };
  stat("ballots counted so far", num(t.ballots_counted));
  stat("registered voters", num(t.registered));
  stat("share of registered", pct(t.share_of_registered));
  stat("vote-by-mail ballots", num(t.vote_by_mail_ballots));
  totals.after(lazyHistory("Ballots counted over time", (body, h) => {
    const series = [{ name: "Ballots counted (all contests)", values: h.ballots_counted }];
    body.append(lineChart(series, h.times, (v) => Math.round(v).toLocaleString("en-US"), "Ballots counted over time"));
    if (h.times.length < 3) body.append(oneTallyNote(h.times));
    body.append(historyTable(h.times.map((tm, i) => [fmtTime(tm), num(h.ballots_counted[i])]).slice(-10).reverse(), ["Tally (county time)", "Ballots counted"]));
  }));
  const sel = document.getElementById("group-select");
  countyData.groups.forEach((g) => sel.append(new Option(`${g.name} (${g.contests.length})`, g.name)));
  sel.addEventListener("change", renderCounty);
  document.getElementById("county-filter").addEventListener("input", renderCounty);
  renderCounty();
}

// ---- tabs -------------------------------------------------------------------
function showTab(name) {
  const county = name === "county";
  document.getElementById("view-city").hidden = county;
  document.getElementById("view-county").hidden = !county;
  document.getElementById("tab-city").setAttribute("aria-selected", String(!county));
  document.getElementById("tab-county").setAttribute("aria-selected", String(county));
  history.replaceState(null, "", county ? "#county" : "#city");
  if (!county && map && cityView) { map.invalidateSize(); map.fitBounds(cityView); }
}

async function start() {
  document.getElementById("tab-city").addEventListener("click", () => showTab("city"));
  document.getElementById("tab-county").addEventListener("click", () => showTab("county"));
  data = await getJSON("data/city_contests.json");
  cityTotals = await getJSON("data/city_totals.json").catch(() => null);
  data.cities.forEach((c) => (byKey[c.key] = c));
  const nCity = data.cities.reduce((n, c) => n + c.contests.length, 0);
  const setStatus = (nOther) => {
    document.getElementById("status").textContent =
      `${data.election.title}, ${data.election.date} · ${nCity} city contests in ${data.cities.length} cities` +
      (nOther === null ? "" : ` · ${nOther} county, state and district contests`) +
      ` · county tally time: ${data.county_time} (county clock)`;
  };
  setStatus(null);
  fillSelects();
  drawLegend();
  showCity(null);
  getJSON("data/county_contests.json").then((d) => { countyData = d; setupCounty(); setStatus(d.groups.reduce((n, g) => n + g.contests.length, 0)); })
    .catch((e) => { document.getElementById("county-note").textContent = "County contests could not be loaded: " + e.message; });
  if (location.hash === "#county") showTab("county");

  map = L.map("map", { zoomSnap: 0.25, attributionControl: false });
  let shapes;
  try { shapes = await getJSON("data/city_boundaries.geojson"); }
  catch (e) {
    document.getElementById("map").append(el("p", "muted", "City boundaries are not loaded yet. Use the city list."));
    return;
  }
  layer = L.geoJSON(shapes, {
    style,
    onEachFeature: (f, lyr) => {
      lyr.bindTooltip(f.properties.name, { sticky: true });
      lyr.on("click", () => {
        const cw = cwContest();
        if (byKey[f.properties.key] || (cw && cw.cities[f.properties.key])) showCity(f.properties.key);
      });
    },
  }).addTo(map);
  // Fit the view to cities that have contests, so remote areas and offshore islands do not shrink the map.
  const view = L.latLngBounds([]);
  layer.eachLayer((l) => { if (l.feature.properties.has_contests) view.extend(l.getBounds()); });
  cityView = view.isValid() ? view.pad(0.03) : layer.getBounds();
  map.fitBounds(cityView);
}
start().catch((e) => { document.getElementById("status").textContent = "Could not load data: " + e.message; });
