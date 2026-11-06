// The map view: color every city by one contest, search for a city, read the details in the side panel.
import { h, num, pct, countyTime, icon, palette, mix, diverging, choiceColor, leaderIndex, titleCase } from "./util.js";
import { S, cityName, getPrecincts, getPrecinctMethod } from "./store.js";
import { combobox, contestCard, resultRows, measureTitleLine, meter } from "./components.js";
import { turnoutByPrecinct, turnoutOf, vbmOf, extremes, scale, MIN_RANK, MIN_SCALE, methodSplit, shareOf, inPersonMinusMail, vbmShareByPrecinct } from "./analysis.js";
import { TOPICS, topicOf } from "./topics.js";
import { navigate, hashFor } from "./router.js";

const REFERENCE_POINT = [34.00929527935462, -118.32913315320754];   // a fixed reference dot, requested by the project owner
let refDot = null, turnout = null, precAvailable = false;
let methodData = null, methodStats = null, methodLoading = false, methodAvailable = false;
// Which ballots a precinct map colours: all of them, only vote-by-mail ballots, only in-person ballots, or the difference between the two.
const METHODS = [["all", "All ballots"], ["vbm", "Vote by mail"], ["ip", "In person"], ["diff", "In person minus mail"]];
const methodOf = () => (["vbm", "ip", "diff"].includes(params.method) ? params.method : "all");
const isAnalysis = (m) => m.type === "turnout" || m.type === "vbm";
const keep = () => ({ precincts: params.precincts, method: params.method });   // settings that survive a change of contest, city or precinct
let built = false, lastContest = null, lastPrecincts = null, map = null, layer = null, lineLayer = null, precLayer = null, prec = null, precLoading = false, precFailed = false, fitBounds = null, params = {}, els = {}, contestBox, cityBox;

// ---- what is being shown ---------------------------------------------------------------------------------------------------
function defaultContest() {
  const gov = S.cwList.find((c) => c.label.toLowerCase() === "governor");
  return gov ? "cw:" + gov.id : S.cwList.length ? "cw:" + S.cwList[0].id : "count";
}
function modeOf(p) {
  const v = p.contest || defaultContest();
  if (v === "turnout") return { type: "turnout", value: "turnout" };
  if (v === "vbm") return { type: "vbm", value: "vbm" };
  if (v.startsWith("cw:") && S.cwById[v.slice(3)]) return { type: "cw", value: v, cw: S.cwById[v.slice(3)] };
  if (v.startsWith("c:") && S.byId["c" + v.slice(2)]) return { type: "city", value: v, contest: S.byId["c" + v.slice(2)] };
  return { type: "count", value: "count" };
}
const focusIndex = (c) => (c.kind === "measure" && c.choices.some((x) => x.name.toUpperCase() === "YES") ? c.choices.findIndex((x) => x.name.toUpperCase() === "YES") : leaderIndex(c.choices));

// blue = the focus choice is ahead (YES, or the county-wide leader), orange = the other side, gray midpoint = a tie
function fillFor(contest, votes, P) {
  const total = votes.reduce((s, v) => s + v, 0);
  if (!total) return P.nodata;
  const share = votes[focusIndex(contest)] / total;
  if (contest.kind === "measure" || contest.choices.length === 2) return diverging(share, P);
  return mix(P.seqLo, P.seqHi, Math.min(share / 0.6, 1));
}
function cellFor(key, m, P) { // {fill, data}
  if (isAnalysis(m)) return { fill: P.nodata, data: false };   // the turnout map is coloured by precinct; cities only show their outline
  if (m.type === "count") { const c = S.cityByKey[key]; return c ? { fill: mix(P.seqLo, P.seqHi, Math.min((c.contests.length - 1) / 5, 1)), data: true } : { fill: P.nodata, data: false }; }
  if (m.type === "cw") { const e = m.cw.cities[key]; return e ? { fill: fillFor(m.cw, e.votes, P), data: true } : { fill: P.nodata, data: false }; }
  return key === m.contest.cityKey ? { fill: fillFor(m.contest, m.contest.choices.map((c) => c.votes), P), data: true } : { fill: P.nodata, data: false };
}
function styleFor(feature) {
  const P = palette(), m = modeOf(params), key = feature.properties.key, cell = cellFor(key, m, P), picked = key === params.city;
  if (precinctsOn(m)) return { fillColor: cell.fill, fillOpacity: 0.12, color: picked ? P.text : P.line, weight: picked ? 2.5 : 1.1, opacity: 1 };
  return { fillColor: cell.fill, fillOpacity: cell.data ? 0.95 : 0.55, color: picked ? P.text : P.line, weight: picked ? 2.5 : 0.6, opacity: 1 };
}
// ---- precinct layer --------------------------------------------------------------------------------------------------------------
// The contest a mode shows by precinct: a countywide contest or a city contest, if the precinct file has votes for it.
const modeContest = (m) => (m.type === "cw" ? m.cw : m.type === "city" ? m.contest : null);
// A contest object for a contest id in the precinct file, or null when the vote order cannot be trusted: the file lists each
// contest's choice names in the order of its vote list, and they must equal the site's names for that contest.
function contestFor(id) {
  const c = S.cwById[id] || S.byId["c" + id], names = prec && prec.names && prec.names[String(id)];
  return c && names && names.length === c.choices.length && names.every((n, i) => n === c.choices[i].name) ? c : null;
}
const hasPrecinctData = (m) => { const c = modeContest(m); return !!(c && prec && contestFor(c.id)); };
const precinctsOn = (m) => (isAnalysis(m) ? !!prec : params.precincts === "1" && hasPrecinctData(m));   // the turnout map is always by precinct
const precinctRow = (m, id) => (prec && prec.votes[id] && modeContest(m) && prec.votes[id].v[String(modeContest(m).id)]) || null;   // [registration, ballots, votes...]
// The votes of one precinct for the shown contest, for the ballots chosen in the toolbar: {votes, ballots} or {diff}; null when the data is missing.
function contestVotes(m, id) {
  const row = precinctRow(m, id), c = modeContest(m);
  if (!row || !c) return null;
  const method = methodOf();
  if (method === "all" || !methodData) return { votes: row.slice(2), ballots: row[1] };
  const mrow = methodData[id] && methodData[id][String(c.id)];
  if (!mrow) return null;
  const sp = methodSplit(row, mrow);
  if (method === "diff") return { diff: inPersonMinusMail(sp, focusIndex(c)) };
  return { votes: sp[method], ballots: sp.ballots[method] };
}
function precinctStyle(feature) {
  const P = palette(), m = modeOf(params), id = feature.properties.id, picked = id === params.precinct;
  const edge = { color: picked ? P.text : P.line, weight: picked ? 2.5 : 0.3, opacity: 1 };
  if (isAnalysis(m)) {
    const stats = m.type === "turnout" ? turnout : methodStats, x = stats && stats.rows.get(id), ok = x && x.rate !== null;
    return { fillColor: ok ? mix(P.seqLo, P.seqHi, scale(x.rate, stats.lo, stats.hi)) : P.nodata, fillOpacity: ok ? 0.95 : 0.5, ...edge };
  }
  const cv = contestVotes(m, id), c = modeContest(m);
  if (cv && cv.diff !== undefined) return { fillColor: cv.diff === null ? P.nodata : diverging(0.5 + cv.diff, P), fillOpacity: cv.diff === null ? 0.5 : 0.95, ...edge };
  const ok = cv && cv.ballots > 0 && cv.votes.some((v) => v > 0);
  return { fillColor: ok ? fillFor(c, cv.votes, P) : P.nodata, fillOpacity: ok ? 0.95 : 0.5, ...edge };
}
function precinctTooltip(feature) {
  const m = modeOf(params), id = feature.properties.id, p = prec.votes[id];
  const head = () => h("div", {}, h("b", {}, `Precinct ${id}`), h("div", { class: "muted" }, p && p.city ? cityName(p.city) || "" : ""));
  if (isAnalysis(m)) {
    const x = (m.type === "turnout" ? turnout : methodStats) && (m.type === "turnout" ? turnout : methodStats).rows.get(id), box = head();
    if (m.type === "turnout") box.append(x && x.rate !== null ? h("div", {}, `${pct(x.rate)} turnout`) : h("div", { class: "muted" }, "No registered voters"), x ? h("div", { class: "muted" }, `${num(x.ballots)} of ${num(x.reg)} registered`) : null);
    else box.append(x && x.rate !== null ? h("div", {}, `${pct(x.rate)} voted by mail`) : h("div", { class: "muted" }, "No ballots counted"), x ? h("div", { class: "muted" }, `${num(x.vbm)} of ${num(x.ballots)} ballots`) : null);
    return box;
  }
  const cv = contestVotes(m, id), c = modeContest(m), box = head();
  if (!cv) { box.append(h("div", { class: "muted" }, methodOf() !== "all" && !methodData ? "Loading…" : "No ballots counted here")); return box; }
  if (cv.diff !== undefined) {
    const name = c.choices[focusIndex(c)].name;
    box.append(cv.diff === null ? h("div", { class: "muted" }, "Not enough votes in one of the groups") : h("div", {}, `${name}: ${Math.abs(cv.diff * 100).toFixed(1)} points ${cv.diff >= 0 ? "higher" : "lower"} in person than by mail`));
    return box;
  }
  const total = cv.votes.reduce((a, b) => a + b, 0);
  if (!cv.ballots || !total) { box.append(h("div", { class: "muted" }, "No ballots counted here")); return box; }
  const i = cv.votes.indexOf(Math.max(...cv.votes)), which = { vbm: " (vote by mail)", ip: " (in person)", all: "" }[methodOf()];
  box.append(h("div", {}, `${c.choices[i].name} ${pct(votesShare(cv.votes, i))}${which}`), h("div", { class: "muted" }, `${num(cv.ballots)} ballots`));
  return box;
}
const votesShare = (votes, i) => shareOf(votes, i);
// City boundary lines drawn ABOVE the precincts (the precincts would otherwise hide them). Not clickable: clicks go to the precinct below.
function lineStyle(feature) {
  const P = palette(), picked = feature.properties.key === params.city;
  return { fill: false, color: P.text, weight: picked ? 3 : 1.6, opacity: picked ? 0.95 : 0.6, interactive: false };
}
function drawLines() {
  if (lineLayer) { map.removeLayer(lineLayer); lineLayer = null; }
  if (!map || !S.shapes || !precinctsOn(modeOf(params))) return;
  if (!map.getPane("cityLines")) { const pane = map.createPane("cityLines"); pane.style.zIndex = 450; pane.style.pointerEvents = "none"; }
  lineLayer = L.geoJSON(S.shapes, { style: lineStyle, pane: "cityLines", interactive: false }).addTo(map);
}
function drawPrecincts() {
  drawLines();
  if (precLayer) { map.removeLayer(precLayer); precLayer = null; }
  const m = modeOf(params);
  if (!map || !precinctsOn(m)) return;
  precLayer = L.geoJSON(prec.shapes, {
    filter: (f) => m.type === "cw" || isAnalysis(m) || !!precinctRow(m, f.properties.id),
    style: precinctStyle,
    onEachFeature: (f, lyr) => {
      lyr.bindTooltip(() => precinctTooltip(f), { sticky: true });
      lyr.on("click", (e) => { L.DomEvent.stopPropagation(e); const p = prec.votes[f.properties.id]; navigate("map", { contest: params.contest, city: p && p.city, ...keep(), precincts: "1", precinct: f.properties.id }); });
      lyr.on("mouseover", () => lyr.setStyle({ weight: 1.6 })); lyr.on("mouseout", () => precLayer.resetStyle(lyr));
    },
  }).addTo(map);
}
function computeStats() {
  if (prec && !turnout) turnout = turnoutByPrecinct(prec, S.cwList.map((c) => c.id));
  if (prec && methodData && !methodStats) methodStats = vbmShareByPrecinct(prec, methodData, S.cwList.map((c) => c.id));
}
async function ensurePrecincts() {
  const m = modeOf(params);
  if ((params.precincts !== "1" && !isAnalysis(m)) || prec || precLoading || precFailed) return;
  precLoading = true; renderToolbarState();
  prec = await getPrecincts(); precLoading = false; precFailed = !prec;
  computeStats();
  renderToolbarState(); update();
}
// The vote-by-mail data is a second file, fetched only when the chosen view needs it.
async function ensureMethod() {
  if (!methodAvailable || methodData || methodLoading) return;
  if (modeOf(params).type !== "vbm" && methodOf() === "all") return;
  methodLoading = true; renderToolbarState();
  methodData = await getPrecinctMethod(); methodLoading = false;
  if (!methodData) methodAvailable = false;
  computeStats(); renderToolbarState(); update();
}
function renderToolbarState() {
  if (!els.precBtn || els.precBtn.hidden) { els.precNote.textContent = ""; els.methodBar.hidden = true; return; }
  const m = modeOf(params), c = modeContest(m), b = els.precBtn, wanted = params.precincts === "1";
  // the "which ballots" buttons: only for a contest shown by precinct, and only if the vote-by-mail file was published
  const showMethods = methodAvailable && !!c && !!prec && precinctsOn(m);
  els.methodBar.hidden = !showMethods;
  if (showMethods) els.methodBar.replaceChildren(h("span", { class: "muted", style: { fontSize: "12.5px", alignSelf: "center" } }, "Ballots:"),
    ...METHODS.map(([k, label]) => h("button", { class: "chip", type: "button", "aria-pressed": String(methodOf() === k), onclick: () => navigate("map", { contest: params.contest, city: params.city, precincts: params.precincts, precinct: params.precinct, method: k === "all" ? "" : k }) }, label)));
  const loading = precLoading || methodLoading;
  if (isAnalysis(m)) { b.setAttribute("aria-pressed", "true"); b.disabled = true; b.title = "This map is always shown by precinct"; els.precNote.textContent = loading ? "Loading precincts…" : precFailed ? "Precinct data has not been published to this site yet." : ""; return; }
  const missing = !!prec && !!c && !hasPrecinctData(m);          // loaded, but this contest is not in the precinct file
  b.setAttribute("aria-pressed", String(wanted && !missing)); b.disabled = !c || missing;
  b.title = !c ? "Pick a contest to see it by precinct" : missing ? "No precinct results for this contest" : "";
  els.precNote.textContent = loading ? "Loading precincts…" : precFailed && wanted ? "Precinct results have not been published to this site yet."
    : !c ? "Precincts: pick a contest" : missing ? "No precinct results for this contest" : "";
}
function tooltipFor(feature) {
  const m = modeOf(params), key = feature.properties.key, name = feature.properties.name === "Unincorporated" ? "Unincorporated areas" : feature.properties.name;
  const box = h("div", {}, h("b", {}, name));
  if (m.type === "count") { const c = S.cityByKey[key]; box.append(h("div", { class: "muted" }, c ? `${c.contests.length} city contest${c.contests.length === 1 ? "" : "s"}` : "No city contests")); }
  else if (m.type === "vbm") {
    const t = methodStats && vbmOf(methodStats, (x) => x.city === key);
    box.append(t && t.n ? h("div", {}, `${pct(t.rate)} voted by mail`) : h("div", { class: "muted" }, "No precinct data"));
  } else if (m.type === "turnout") {
    const t = turnout && turnoutOf(turnout, (x) => x.city === key);
    box.append(t && t.n ? h("div", {}, `${pct(t.rate)} turnout`) : h("div", { class: "muted" }, "No precinct data"), t && t.n ? h("div", { class: "muted" }, `${num(t.ballots)} of ${num(t.reg)} registered`) : null);
  } else if (m.type === "cw") {
    const e = m.cw.cities[key];
    if (!e) box.append(h("div", { class: "muted" }, "No precinct data"));
    else { const total = e.votes.reduce((s, v) => s + v, 0), i = e.votes.indexOf(Math.max(...e.votes)); box.append(h("div", {}, `${m.cw.choices[i].name} ${pct(total ? e.votes[i] / total : null)}`), h("div", { class: "muted" }, `${num(e.ballots)} ballots`)); }
  } else if (key === m.contest.cityKey) {
    const top = [...m.contest.choices].sort((a, b) => b.votes - a.votes)[0]; box.append(h("div", {}, `${top.name} ${pct(top.share)}`));
  } else box.append(h("div", { class: "muted" }, "Not part of this contest"));
  return box;
}

// ---- legend ---------------------------------------------------------------------------------------------------------------------
function legendFor(m) {
  const P = palette(), box = h("div", { class: "map-legend" });
  const item = (color, text) => h("div", { class: "legend-item" }, h("span", { class: "key", style: { background: color } }), text);
  const ramp = (css, left, right, mid) => h("div", {}, h("div", { class: "ramp", style: { background: css } }), h("div", { class: "ramp-labels" }, h("span", {}, left), mid && h("span", {}, mid), h("span", {}, right)));
  if (m.type === "turnout") {
    box.append(h("div", { class: "title" }, "Turnout by precinct"));
    if (turnout) box.append(ramp(`linear-gradient(90deg, ${P.seqLo}, ${P.seqHi})`, pct(turnout.lo, 0), pct(turnout.hi, 0)), h("div", { class: "note" }, "Ballots cast as a share of registered voters. The scale runs from the 5th to the 95th percentile of precincts."));
    else box.append(h("div", { class: "note" }, "Loading…"));
    box.append(item(P.nodata, "No registered voters"), h("div", { class: "legend-item" }, h("span", { class: "key", style: { background: "transparent", borderTop: `2px solid ${P.text}`, height: "0", borderRadius: "0" } }), "City boundary"));
    return box;
  }
  if (m.type === "vbm") {
    box.append(h("div", { class: "title" }, "Vote-by-mail share of ballots"));
    if (methodStats) box.append(ramp(`linear-gradient(90deg, ${P.seqLo}, ${P.seqHi})`, pct(methodStats.lo, 0), pct(methodStats.hi, 0)), h("div", { class: "note" }, "Ballots cast by mail as a share of all ballots counted in the precinct. The scale runs from the 5th to the 95th percentile."));
    else box.append(h("div", { class: "note" }, "Loading…"));
    box.append(item(P.nodata, "No ballots counted"), h("div", { class: "legend-item" }, h("span", { class: "key", style: { background: "transparent", borderTop: `2px solid ${P.text}`, height: "0", borderRadius: "0" } }), "City boundary"));
    return box;
  }
  if (m.type === "count") box.append(h("div", { class: "title" }, "Cities with their own contests"), ramp(`linear-gradient(90deg, ${P.seqLo}, ${P.seqHi})`, "1 contest", "6 or more"), item(P.nodata, "No contests on this ballot"));
  else {
    const c = m.type === "cw" ? m.cw : m.contest, f = focusIndex(c);
    box.append(h("div", { class: "title" }, titleCase(c.label)));
    const method = precinctsOn(m) ? methodOf() : "all";
    if (method === "diff") {
      box.append(ramp(`linear-gradient(90deg, ${P.b}, ${P.mid}, ${P.a})`, "better by mail", "better in person", "same"),
        h("div", { class: "note" }, `Where ${c.choices[f].name} did better in person than by mail (blue) or by mail than in person (orange). Full color at a 30-point gap.`),
        item(P.nodata, "Not enough votes in one of the groups"));
      if (precinctsOn(m)) box.append(h("div", { class: "legend-item" }, h("span", { class: "key", style: { background: "transparent", borderTop: `2px solid ${P.text}`, height: "0", borderRadius: "0" } }), "City boundary"));
      return box;
    }
    if (method !== "all") box.append(h("div", { class: "note" }, method === "vbm" ? "Vote-by-mail ballots only." : "In-person ballots only."));
    if (c.kind === "measure" || c.choices.length === 2) {
      const other = c.choices[c.choices.length === 2 ? 1 - f : 0].name;
      box.append(ramp(`linear-gradient(90deg, ${P.b}, ${P.mid}, ${P.a})`, `${other} ahead`, `${c.choices[f].name} ahead`, "even"), h("div", { class: "note" }, "Full color at a 30-point lead."));
    } else box.append(ramp(`linear-gradient(90deg, ${P.seqLo}, ${P.seqHi})`, "0%", "60%+"), h("div", { class: "note" }, `${c.choices[f].name}'s share of the vote in each city.`));
    box.append(item(P.nodata, m.type === "cw" ? "No precinct data" : "Not part of this contest"));
    if (precinctsOn(m)) box.append(h("div", { class: "legend-item" }, h("span", { class: "key", style: { background: "transparent", borderTop: `2px solid ${P.text}`, height: "0", borderRadius: "0" } }), "City boundary"));
  }
  return box;
}

// ---- side panel -------------------------------------------------------------------------------------------------------------------
function sourceNote() {
  const t = (S.totals && S.totals.tally) || {};
  const status = (t.svc_status || []).join(", ").toLowerCase() || "precinct file";
  return [`Source: the county's precinct-level Statement of Votes Cast (${status}), matched to the county tally of ${countyTime(t.county_time)}` +
    (t.largest_difference ? ` (every total within ${(t.largest_difference * 100).toFixed(2)}%).` : "."),
    t.is_latest === false ? ` The live county totals are newer (${countyTime(t.latest_county_time)}), so these city numbers trail them.` : "",
    " Each precinct is placed in the city whose boundary covers most of it, or in unincorporated areas."].join("");
}
function cwCity(cw, key) {
  const e = cw.cities[key];
  const card = h("div", { class: "inline-card accent" }, h("div", { class: "tag" }, "Countywide contest, this area"), h("h3", { class: "contest-title" }, titleCase(cw.label)), measureTitleLine(cw));
  if (!e) { card.append(h("p", { class: "note" }, "No precinct-level data for this area.")); return card; }
  const total = e.votes.reduce((s, v) => s + v, 0);
  card.append(resultRows(cw.choices.map((c, i) => ({ name: c.name, party: c.party, votes: e.votes[i], share: total ? e.votes[i] / total : null, color: choiceColor(cw, i) }))),
    h("div", { class: "contest-meta" }, h("span", {}, `${num(e.ballots)} ballots`), h("span", {}, `${num(e.registration)} registered`)));
  if (e.fallback_ballots > 0) card.append(h("p", { class: "note" }, `${pct(e.fallback_ballots / e.ballots)} of these ballots were placed by place name because no precinct shape was found.`));
  card.append(h("details", { class: "more" }, h("summary", {}, "About these numbers"), h("p", { class: "note more-body" }, sourceNote())));
  return card;
}
// ---- turnout panel ----------------------------------------------------------------------------------------------------------------
function turnoutCard(rate, reg, ballots, label) {
  return h("div", { class: "inline-card accent" }, h("div", { class: "tag" }, label),
    h("div", { class: "num", style: { fontSize: "34px", fontWeight: "680", letterSpacing: "-.02em", lineHeight: "1.1" } }, pct(rate)),
    meter(rate || 0, "Share of registered voters who cast a ballot"),
    h("div", { class: "contest-meta" }, h("span", {}, `${num(ballots)} ballots`), h("span", {}, `${num(reg)} registered`)));
}
function turnoutPanel(key) {
  const box = els.panel, name = key ? cityName(key) : null;
  if (!turnout) { box.append(h("h2", { class: "panel-title" }, "Turnout"), h("p", { class: "note" }, precFailed ? "Precinct data has not been published to this site yet." : "Loading precincts…")); return; }
  const inCity = key ? (x) => x.city === key : null, t = turnoutOf(turnout, inCity), county = turnoutOf(turnout);
  box.append(h("div", { class: "stack" }, h("h2", { class: "panel-title" }, name || "Turnout by precinct"),
    key ? h("div", {}, h("a", { class: "btn small", href: hashFor("map", { contest: "turnout" }) }, "Clear selection")) : null));
  box.append(turnoutCard(t.rate, t.reg, t.ballots, key ? `${name}: ${num(t.n)} precincts` : `All ${num(county.n)} precincts`));
  if (key) box.append(h("p", { class: "note" }, `County overall in the same file: ${pct(county.rate)}.`));
  const e = extremes(turnout, 5, inCity);
  const list = (title, items) => h("div", { class: "stack" }, h("h3", { class: "section-title", style: { fontSize: "15px" } }, title),
    h("div", { class: "rank-list" }, items.map((x) => h("a", { class: "rank-row", href: hashFor("map", { contest: "turnout", city: x.city, precinct: x.id }) },
      h("span", {}, h("b", {}, x.id), h("small", {}, x.city ? cityName(x.city) || "" : "")), h("span", { class: "num" }, `${pct(x.rate)}`, h("small", {}, `${num(x.ballots)} of ${num(x.reg)}`))))));
  if (e.eligible >= 2) box.append(list("Highest turnout", e.highest), list("Lowest turnout", e.lowest),
    h("p", { class: "note" }, `Lists include precincts with at least ${num(MIN_RANK)} registered voters (${num(e.eligible)} ${key ? "here" : "in all"}), so a handful of voters cannot top them.`));
  box.append(h("p", { class: "note" }, `Ballots cast in a precinct is the most ballots any countywide contest recorded there; across the county that matches the county's own ballots-counted at this tally to within 0.01%. From the county's precinct-level Statement of Votes Cast, at the tally of ${countyTime(((S.totals || {}).tally || {}).county_time)}, which trails the live count, so turnout will be higher once counting finishes. Turnout above 100% can occur where registration is out of date.`));
  if (key && S.cityByKey[key]) box.append(h("h3", { class: "section-title", style: { fontSize: "15px" } }, `City contests in ${name}`, h("small", {}, String(S.cityByKey[key].contests.length))), ...S.cityByKey[key].contests.map((c) => contestCard(c, {})));
}
// ---- vote-by-mail panel -------------------------------------------------------------------------------------------------------------
function mailCard(rate, vbm, ballots, label) {
  return h("div", { class: "inline-card accent" }, h("div", { class: "tag" }, label),
    h("div", { class: "num", style: { fontSize: "34px", fontWeight: "680", letterSpacing: "-.02em", lineHeight: "1.1" } }, pct(rate)),
    meter(rate || 0, "Share of ballots cast by mail"),
    h("div", { class: "contest-meta" }, h("span", {}, `${num(vbm)} by mail`), h("span", {}, `${num(ballots - vbm)} in person`), h("span", {}, `${num(ballots)} ballots`)));
}
const MAIL_NOTE = "From the county's precinct-level Statement of Votes Cast, which prints vote-by-mail and in-person rows for every precinct. Ballots are the most any countywide contest recorded in the precinct. This is the mix of the ballots counted at that tally, not of all ballots that will be counted: late mail ballots are still arriving.";
function vbmPanel(key) {
  const box = els.panel, name = key ? cityName(key) : null;
  if (!methodStats) { box.append(h("h2", { class: "panel-title" }, "Vote by mail"), h("p", { class: "note" }, methodAvailable || precLoading || methodLoading ? "Loading precincts…" : "Vote-by-mail data has not been published to this site yet.")); return; }
  const inCity = key ? (x) => x.city === key : null, t = vbmOf(methodStats, inCity), all = vbmOf(methodStats);
  box.append(h("div", { class: "stack" }, h("h2", { class: "panel-title" }, name || "Vote by mail, by precinct"),
    key ? h("div", {}, h("a", { class: "btn small", href: hashFor("map", { contest: "vbm" }) }, "Clear selection")) : null));
  box.append(mailCard(t.rate, t.vbm, t.ballots, key ? `${name}: ${num(t.n)} precincts` : `All ${num(all.n)} precincts`));
  if (key) box.append(h("p", { class: "note" }, `County overall in the same file: ${pct(all.rate)} by mail.`));
  const e = extremes(methodStats, 5, inCity, MIN_SCALE);
  const list = (title, items) => h("div", { class: "stack" }, h("h3", { class: "section-title", style: { fontSize: "15px" } }, title),
    h("div", { class: "rank-list" }, items.map((x) => h("a", { class: "rank-row", href: hashFor("map", { contest: "vbm", city: x.city, precinct: x.id }) },
      h("span", {}, h("b", {}, x.id), h("small", {}, x.city ? cityName(x.city) || "" : "")), h("span", { class: "num" }, pct(x.rate), h("small", {}, `${num(x.vbm)} of ${num(x.ballots)}`))))));
  if (e.eligible >= 2) box.append(list("Most by mail", e.highest), list("Most in person", e.lowest),
    h("p", { class: "note" }, `Lists include precincts with at least ${num(MIN_SCALE)} ballots (${num(e.eligible)} ${key ? "here" : "in all"}).`));
  box.append(h("p", { class: "note" }, MAIL_NOTE));
  if (key && S.cityByKey[key]) box.append(h("h3", { class: "section-title", style: { fontSize: "15px" } }, `City contests in ${name}`, h("small", {}, String(S.cityByKey[key].contests.length))), ...S.cityByKey[key].contests.map((c) => contestCard(c, {})));
}
// One contest in one precinct, side by side: every ballot, vote-by-mail ballots, in-person ballots.
function splitTable(contest, row, mrow) {
  const sp = methodSplit(row, mrow), order = contest.choices.map((c, i) => i).sort((a, b) => sp.all[b] - sp.all[a]);
  const cell = (votes, i) => h("td", { class: "num" }, pct(shareOf(votes, i)));
  return h("div", { class: "split" }, h("table", { class: "split-table" },
    h("thead", {}, h("tr", {}, h("th", {}, "Share of votes"), h("th", {}, "All"), h("th", {}, "By mail"), h("th", {}, "In person"))),
    h("tbody", {}, order.map((i) => h("tr", {}, h("td", {}, contest.choices[i].name), cell(sp.all, i), cell(sp.vbm, i), cell(sp.ip, i))),
      h("tr", { class: "total" }, h("td", {}, "Ballots"), h("td", { class: "num" }, num(sp.ballots.all)), h("td", { class: "num" }, num(sp.ballots.vbm)), h("td", { class: "num" }, num(sp.ballots.ip))))));
}
function precinctPanel(m, id) {
  const p = prec && prec.votes[id], box = els.panel, name = p && p.city ? cityName(p.city) : null;
  box.append(h("div", { class: "stack" }, h("p", { class: "tag" }, "Precinct"), h("h2", { class: "panel-title" }, id),
    h("div", { class: "muted" }, name ? (p.city === "unincorporated" ? "Unincorporated areas" : name) : ""),
    h("div", {}, h("a", { class: "btn small", href: hashFor("map", { contest: params.contest, city: params.city, ...keep(), precincts: "1" }) }, "Back to " + (name || "the map")))));
  if (!p) { box.append(h("p", { class: "note" }, "No results for this precinct.")); return; }
  const one = (cw, row, title) => {
    const votes = row.slice(2), total = votes.reduce((a, b) => a + b, 0);
    return h("div", { class: "inline-card" + (title ? "" : " accent") }, h("h3", { class: "contest-title" }, titleCase(cw.label)), measureTitleLine(cw),
      row[1] ? resultRows(cw.choices.map((c, i) => ({ name: c.name, party: c.party, votes: votes[i], share: total ? votes[i] / total : null, color: choiceColor(cw, i) }))) : h("p", { class: "note" }, "No ballots counted in this precinct."),
      h("div", { class: "contest-meta" }, h("span", {}, `${num(row[1])} ballots`), h("span", {}, `${num(row[0])} registered`)));
  };
  if (m.type === "vbm") {
    const x = methodStats && methodStats.rows.get(id);
    if (x) box.append(mailCard(x.rate, x.vbm, x.ballots, "Vote by mail in this precinct"), h("p", { class: "note" }, `County overall in the same file: ${pct(vbmOf(methodStats).rate)} by mail.`));
  }
  if (m.type === "turnout") {
    const x = turnout && turnout.rows.get(id);
    if (x) box.append(turnoutCard(x.rate, x.reg, x.ballots, "Turnout in this precinct"), h("p", { class: "note" }, `County overall in the same file: ${pct(turnoutOf(turnout).rate)}.`));
  }
  const row = precinctRow(m, id), shown = modeContest(m);
  if (row && shown) {
    box.append(one(shown, row, false));
    const mrow = methodData && methodData[id] && methodData[id][String(shown.id)];
    if (mrow) box.append(splitTable(shown, row, mrow));
  }
  const others = Object.keys(p.v).map((cid) => contestFor(cid)).filter((c) => c && (!shown || c.id !== shown.id))
    .sort((a, b) => (a.cityKey ? 1 : 0) - (b.cityKey ? 1 : 0) || titleCase(a.label).localeCompare(titleCase(b.label)));
  if (others.length) box.append(h("details", { class: "more" }, h("summary", {}, `All ${others.length + (row ? 1 : 0)} contests in this precinct`),
    h("div", { class: "more-body stack" }, others.map((c) => { const card = one(c, p.v[String(c.id)], true); if (c.city) card.prepend(h("span", { class: "tag" }, c.city)); return card; }))));
  box.append(h("p", { class: "note" }, "From the county's precinct-level Statement of Votes Cast, at the same tally as the city numbers (which can trail the live count). Shapes are the county's consolidated election precincts, matched by precinct number. Small precincts have small counts, so shares can swing widely."));
}
function renderPanel() {
  const m = modeOf(params), key = params.city || "", box = els.panel;
  box.replaceChildren();
  if (params.precinct && precinctsOn(m) && prec.votes[params.precinct]) { precinctPanel(m, params.precinct); return; }
  if (m.type === "turnout") { turnoutPanel(key); return; }
  if (m.type === "vbm") { vbmPanel(key); return; }
  const name = key ? cityName(key) : null;
  if (!key || !name) {
    box.append(h("h2", { class: "panel-title" }, "Pick an area"));
    if (m.type === "cw") {
      const cw = m.cw, total = cw.choices.reduce((s, c) => s + c.county_votes, 0);
      box.append(h("div", { class: "inline-card accent" }, h("div", { class: "tag" }, "Countywide"), h("h3", { class: "contest-title" }, titleCase(cw.label)), measureTitleLine(cw),
        resultRows(cw.choices.map((c, i) => ({ name: c.name, party: c.party, votes: c.county_votes, share: total ? c.county_votes / total : null, color: choiceColor(cw, i) }))),
        h("p", { class: "note" }, "County totals at the tally the city numbers come from, which can trail the live count.")));
    } else if (m.type === "city") box.append(contestCard(m.contest, { compact: true, kicker: m.contest.city }));
    box.append(h("div", { class: "empty-state" }, icon("pin", 22), h("p", {}, "Click a city on the map, or search for one above, to see its results.")));
    return;
  }
  const city = S.cityByKey[key];
  box.append(h("div", { class: "stack" }, h("h2", { class: "panel-title" }, name),
    h("div", {}, h("a", { class: "btn small", href: hashFor("map", { contest: params.contest, ...keep() }) }, "Clear selection"))));
  if (m.type === "cw") box.append(cwCity(m.cw, key));
  if (city) {
    const contests = [...city.contests].sort((a, b) => (m.type === "city" && a.id === m.contest.id ? -1 : 0) - (m.type === "city" && b.id === m.contest.id ? -1 : 0));
    box.append(h("h3", { class: "section-title", style: { fontSize: "15px" } }, `City contests in ${name}`, h("small", {}, String(contests.length))), ...contests.map((c) => contestCard(c, {})));
  } else box.append(h("p", { class: "note" }, key === "unincorporated" ? "Unincorporated areas have no city contests." : `${name} has no contests of its own on this ballot.`));
  box.scrollTop = 0;
}

// ---- building and updating -----------------------------------------------------------------------------------------------------------
function cityOptions() {
  const keys = new Map(S.city.cities.map((c) => [c.key, c.name]));
  for (const cw of S.cwList) for (const [k, v] of Object.entries(cw.cities)) if (!keys.has(k)) keys.set(k, v.name);
  return [{ label: "", options: [...keys].sort((a, b) => a[1].localeCompare(b[1])).map(([value, label]) => ({ value, label })) }];
}
function contestGroups() {
  const groups = [{ label: "", options: [{ value: "count", label: "Which cities have their own contests" }] }];
  if (precAvailable) groups.push({ label: "Precinct analyses", options: [{ value: "turnout", label: "Turnout by precinct" }, ...(methodAvailable ? [{ value: "vbm", label: "Vote-by-mail share of ballots" }] : [])] });
  if (S.cwList.length) {
    const by = {};
    for (const cw of S.cwList) (by[topicOf(cw.group)] ||= []).push(cw);
    for (const t of [...TOPICS, { id: "other", label: "Other" }]) if (by[t.id]) groups.push({ label: `${t.label}: results by city`, options: by[t.id].map((cw) => ({ value: "cw:" + cw.id, label: titleCase(cw.label) })) });
  } else groups.push({ label: "Results by city", options: [{ value: "", label: "Not published by the county yet", disabled: true }] });
  for (const city of S.city.cities) groups.push({ label: `${city.name}: city contests`, options: city.contests.map((c) => ({ value: "c:" + c.id, label: `${city.name}: ${titleCase(c.label)}` })) });
  return groups;
}
function restyle() { if (layer) layer.setStyle(styleFor); if (precLayer) precLayer.setStyle(precinctStyle); if (lineLayer) lineLayer.setStyle(lineStyle); }
function update() { drawPrecincts(); restyle(); renderLegend(); renderPanel(); renderToolbarState(); }
function renderLegend() { els.legend.replaceChildren(legendFor(modeOf(params))); }

function build(root, ctx) {
  built = true;
  contestBox = combobox({ label: "Show on the map", placeholder: "Search contests, e.g. Governor, Measure A, Mayor", groups: contestGroups, value: modeOf(params).value,
    onChange: (v) => navigate("map", { contest: v, city: params.city, ...keep() }) });
  cityBox = combobox({ label: "Find a city", placeholder: "Search cities", groups: cityOptions, value: params.city || "", emptyText: "No city with that name",
    onChange: (v) => navigate("map", { contest: params.contest, city: v, ...keep() }) });
  els.legend = h("div", {});
  els.precNote = h("span", { class: "note", role: "status" });
  els.methodBar = h("div", { class: "chips", role: "group", "aria-label": "Which ballots to show", hidden: true });
  els.precBtn = h("button", { class: "chip", type: "button", "aria-pressed": "false", hidden: true, onclick: () => navigate("map", { contest: params.contest, city: params.city, method: params.method, precincts: params.precincts === "1" ? "" : "1" }) }, icon("pin", 14), "Precincts");
  // The precinct layer is only offered when the site was built with precinct data (see sitegen/precincts.py).
  fetch("data/precincts.geojson", { method: "HEAD" }).then((r) => { if (r.ok) {
    precAvailable = true; els.precBtn.hidden = false; contestBox.refresh(); renderToolbarState(); ensurePrecincts();
    fetch("data/precincts_method.json", { method: "HEAD" }).then((q) => { if (q.ok) { methodAvailable = true; contestBox.refresh(); renderToolbarState(); ensureMethod(); } }).catch(() => {});
  } }).catch(() => {});
  els.panel = h("div", { class: "card panel", "aria-live": "polite" });
  els.mapEl = h("div", { id: "map", role: "region", "aria-label": "Map of Los Angeles County. Use the city search for a keyboard-friendly alternative." });
  els.source = S.totals ? h("button", { class: "chip map-source", type: "button", onclick: ctx.openAbout }, icon("info", 14), "About the by-city numbers") : null;
  root.replaceChildren(
    h("div", {}, h("h1", { class: "page-title" }, "Results map"), h("p", { class: "page-lede" }, "Color the map by any contest and click a city for its numbers. Countywide contests are summed from the county's precinct results.")),
    h("div", { class: "card toolbar" }, contestBox.el, cityBox.el, els.precBtn, els.precNote, els.methodBar, h("button", { class: "btn", type: "button", onclick: () => map && fitBounds && map.fitBounds(fitBounds) }, icon("reset", 16), "Reset view")),
    h("div", { class: "map-layout" }, h("div", { class: "card map-card" }, els.mapEl, els.legend, els.source), els.panel));
  if (!S.shapes) { els.mapEl.append(h("div", { class: "empty-state" }, h("p", {}, "The city boundaries are not available right now. The city search and the results panel still work."))); return; }
  map = L.map(els.mapEl, { zoomSnap: 0.25, zoomDelta: 0.5, attributionControl: false });
  layer = L.geoJSON(S.shapes, {
    style: styleFor,
    onEachFeature: (f, lyr) => {
      lyr.bindTooltip(() => tooltipFor(f), { sticky: true });
      lyr.on("click", () => { const m = modeOf(params), k = f.properties.key; if (S.cityByKey[k] || isAnalysis(m) || (m.type === "cw" && m.cw.cities[k]) || k === "unincorporated") navigate("map", { contest: params.contest, city: k, ...keep() }); });
      lyr.on("mouseover", () => lyr.setStyle({ weight: 1.6 })); lyr.on("mouseout", () => layer.resetStyle(lyr));
    },
  }).addTo(map);
  const view = L.latLngBounds([]);
  layer.eachLayer((l) => { if (l.feature.properties.has_contests) view.extend(l.getBounds()); });
  fitBounds = view.isValid() ? view.pad(0.03) : layer.getBounds();
  // Reference dot, above the precincts and city lines. Small, with a surface-coloured ring so it reads on any fill, light or dark.
  const refStyle = () => { const P = palette(); return { radius: 5, color: P.surface || "#fff", weight: 2, fillColor: P.text, fillOpacity: 1, opacity: 1 }; };
  map.createPane("refPoint").style.zIndex = 480;
  refDot = L.circleMarker(REFERENCE_POINT, { ...refStyle(), pane: "refPoint", interactive: false }).addTo(map);   // just a dot: no label, clicks pass through
  window.addEventListener("themechange", () => { restyle(); renderLegend(); refDot.setStyle(refStyle()); });
  // precinct state is not carried when switching contests unless it still applies
}

export function updateMap(root, p, ctx) {
  const first = !built;
  params = p;
  if (first) build(root, ctx);
  const m = modeOf(params);
  contestBox.set(m.value); cityBox.set(params.city || "");
  const contestChanged = lastContest !== params.contest || lastPrecincts !== params.precincts; lastContest = params.contest; lastPrecincts = params.precincts;
  update(); ensurePrecincts(); ensureMethod();
  if (map) {
    map.invalidateSize();
    if (first) map.fitBounds(fitBounds);
    if ((first || contestChanged) && m.type === "city" && params.precincts === "1" && !params.precinct) {   // a city contest by precinct: zoom to that city
      const box = L.latLngBounds([]);     // a city can be several shapes (Los Angeles has a harbor strip): use all of them
      if (layer) layer.eachLayer((l) => { if (l.feature.properties.key === m.contest.cityKey) box.extend(l.getBounds()); });
      if (box.isValid()) map.fitBounds(box.pad(0.05));
    }
    if (params.precinct && precLayer) { const lyr = precLayer.getLayers().find((l) => l.feature.properties.id === params.precinct); if (lyr) map.fitBounds(lyr.getBounds().pad(1.5), { maxZoom: 15 }); }
  }
}
