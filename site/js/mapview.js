// The map view: color every city by one contest, search for a city, read the details in the side panel.
import { h, num, pct, countyTime, icon, palette, mix, diverging, choiceColor, leaderIndex, titleCase } from "./util.js";
import { S, cityName, getPrecincts } from "./store.js";
import { combobox, contestCard, resultRows } from "./components.js";
import { TOPICS, topicOf } from "./topics.js";
import { navigate, hashFor } from "./router.js";

let built = false, map = null, layer = null, lineLayer = null, precLayer = null, prec = null, precLoading = false, precFailed = false, fitBounds = null, params = {}, els = {}, contestBox, cityBox;

// ---- what is being shown ---------------------------------------------------------------------------------------------------
function defaultContest() {
  const gov = S.cwList.find((c) => c.label.toLowerCase() === "governor");
  return gov ? "cw:" + gov.id : S.cwList.length ? "cw:" + S.cwList[0].id : "count";
}
function modeOf(p) {
  const v = p.contest || defaultContest();
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
const precinctsOn = (m) => params.precincts === "1" && m.type === "cw" && !!prec;
const precinctRow = (m, id) => (prec && prec.votes[id] && prec.votes[id].v[String(m.cw.id)]) || null;   // [registration, ballots, votes...]
function precinctStyle(feature) {
  const P = palette(), m = modeOf(params), id = feature.properties.id, row = m.type === "cw" ? precinctRow(m, id) : null, picked = id === params.precinct;
  const votes = row ? row.slice(2) : [];
  return { fillColor: row && row[1] > 0 ? fillFor(m.cw, votes, P) : P.nodata, fillOpacity: row && row[1] > 0 ? 0.95 : 0.5, color: picked ? P.text : P.line, weight: picked ? 2.5 : 0.3, opacity: 1 };
}
function precinctTooltip(feature) {
  const m = modeOf(params), id = feature.properties.id, row = precinctRow(m, id), p = prec.votes[id];
  const box = h("div", {}, h("b", {}, `Precinct ${id}`), h("div", { class: "muted" }, p && p.city ? cityName(p.city) || "" : ""));
  if (!row || !row[1]) { box.append(h("div", { class: "muted" }, "No ballots counted here")); return box; }
  const votes = row.slice(2), total = votes.reduce((a, b) => a + b, 0), i = votes.indexOf(Math.max(...votes));
  box.append(h("div", {}, `${m.cw.choices[i].name} ${pct(total ? votes[i] / total : null)}`), h("div", { class: "muted" }, `${num(row[1])} ballots`));
  return box;
}
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
    style: precinctStyle,
    onEachFeature: (f, lyr) => {
      lyr.bindTooltip(() => precinctTooltip(f), { sticky: true });
      lyr.on("click", (e) => { L.DomEvent.stopPropagation(e); const p = prec.votes[f.properties.id]; navigate("map", { contest: params.contest, city: p && p.city, precincts: "1", precinct: f.properties.id }); });
      lyr.on("mouseover", () => lyr.setStyle({ weight: 1.6 })); lyr.on("mouseout", () => precLayer.resetStyle(lyr));
    },
  }).addTo(map);
}
async function ensurePrecincts() {
  if (params.precincts !== "1" || prec || precLoading || precFailed) return;
  precLoading = true; renderToolbarState();
  prec = await getPrecincts(); precLoading = false; precFailed = !prec;
  renderToolbarState(); update();
}
function renderToolbarState() {
  if (!els.precBtn || els.precBtn.hidden) { els.precNote.textContent = ""; return; }
  const m = modeOf(params), on = params.precincts === "1" && m.type === "cw", b = els.precBtn;
  b.setAttribute("aria-pressed", String(on)); b.disabled = m.type !== "cw";
  b.title = m.type !== "cw" ? "Precinct results are available for countywide contests" : "";
  els.precNote.textContent = precLoading ? "Loading precincts…" : precFailed && params.precincts === "1" ? "Precinct results have not been published to this site yet." : m.type !== "cw" ? "Precincts: pick a countywide contest" : "";
}
function tooltipFor(feature) {
  const m = modeOf(params), key = feature.properties.key, name = feature.properties.name === "Unincorporated" ? "Unincorporated areas" : feature.properties.name;
  const box = h("div", {}, h("b", {}, name));
  if (m.type === "count") { const c = S.cityByKey[key]; box.append(h("div", { class: "muted" }, c ? `${c.contests.length} city contest${c.contests.length === 1 ? "" : "s"}` : "No city contests")); }
  else if (m.type === "cw") {
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
  if (m.type === "count") box.append(h("div", { class: "title" }, "Cities with their own contests"), ramp(`linear-gradient(90deg, ${P.seqLo}, ${P.seqHi})`, "1 contest", "6 or more"), item(P.nodata, "No contests on this ballot"));
  else {
    const c = m.type === "cw" ? m.cw : m.contest, f = focusIndex(c);
    box.append(h("div", { class: "title" }, titleCase(c.label)));
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
  const card = h("div", { class: "inline-card accent" }, h("div", { class: "tag" }, "Countywide contest, this area"), h("h3", { class: "contest-title" }, titleCase(cw.label)));
  if (!e) { card.append(h("p", { class: "note" }, "No precinct-level data for this area.")); return card; }
  const total = e.votes.reduce((s, v) => s + v, 0);
  card.append(resultRows(cw.choices.map((c, i) => ({ name: c.name, party: c.party, votes: e.votes[i], share: total ? e.votes[i] / total : null, color: choiceColor(cw, i) }))),
    h("div", { class: "contest-meta" }, h("span", {}, `${num(e.ballots)} ballots`), h("span", {}, `${num(e.registration)} registered`)));
  if (e.fallback_ballots > 0) card.append(h("p", { class: "note" }, `${pct(e.fallback_ballots / e.ballots)} of these ballots were placed by place name because no precinct shape was found.`));
  card.append(h("details", { class: "more" }, h("summary", {}, "About these numbers"), h("p", { class: "note more-body" }, sourceNote())));
  return card;
}
function precinctPanel(m, id) {
  const p = prec && prec.votes[id], box = els.panel, name = p && p.city ? cityName(p.city) : null;
  box.append(h("div", { class: "stack" }, h("p", { class: "tag" }, "Precinct"), h("h2", { class: "panel-title" }, id),
    h("div", { class: "muted" }, name ? (p.city === "unincorporated" ? "Unincorporated areas" : name) : ""),
    h("div", {}, h("a", { class: "btn small", href: hashFor("map", { contest: params.contest, city: params.city, precincts: "1" }) }, "Back to " + (name || "the map")))));
  if (!p) { box.append(h("p", { class: "note" }, "No results for this precinct.")); return; }
  const one = (cw, row, title) => {
    const votes = row.slice(2), total = votes.reduce((a, b) => a + b, 0);
    return h("div", { class: "inline-card" + (title ? "" : " accent") }, h("h3", { class: "contest-title" }, titleCase(cw.label)),
      row[1] ? resultRows(cw.choices.map((c, i) => ({ name: c.name, party: c.party, votes: votes[i], share: total ? votes[i] / total : null, color: choiceColor(cw, i) }))) : h("p", { class: "note" }, "No ballots counted in this precinct."),
      h("div", { class: "contest-meta" }, h("span", {}, `${num(row[1])} ballots`), h("span", {}, `${num(row[0])} registered`)));
  };
  const row = m.type === "cw" && precinctRow(m, id);
  if (row) box.append(one(m.cw, row, false));
  const others = S.cwList.filter((cw) => p.v[String(cw.id)] && (m.type !== "cw" || cw.id !== m.cw.id));
  if (others.length) box.append(h("details", { class: "more" }, h("summary", {}, `All ${others.length + (row ? 1 : 0)} countywide contests in this precinct`),
    h("div", { class: "more-body stack" }, others.map((cw) => one(cw, p.v[String(cw.id)], true)))));
  box.append(h("p", { class: "note" }, "From the county's precinct-level Statement of Votes Cast, at the same tally as the city numbers (which can trail the live count). Shapes are the county's consolidated election precincts, matched by precinct number. Small precincts have small counts, so shares can swing widely."));
}
function renderPanel() {
  const m = modeOf(params), key = params.city || "", box = els.panel;
  box.replaceChildren();
  if (params.precinct && precinctsOn(m) && prec.votes[params.precinct]) { precinctPanel(m, params.precinct); return; }
  const name = key ? cityName(key) : null;
  if (!key || !name) {
    box.append(h("h2", { class: "panel-title" }, "Pick an area"));
    if (m.type === "cw") {
      const cw = m.cw, total = cw.choices.reduce((s, c) => s + c.county_votes, 0);
      box.append(h("div", { class: "inline-card accent" }, h("div", { class: "tag" }, "Countywide"), h("h3", { class: "contest-title" }, titleCase(cw.label)),
        resultRows(cw.choices.map((c, i) => ({ name: c.name, party: c.party, votes: c.county_votes, share: total ? c.county_votes / total : null, color: choiceColor(cw, i) }))),
        h("p", { class: "note" }, "County totals at the tally the city numbers come from, which can trail the live count.")));
    } else if (m.type === "city") box.append(contestCard(m.contest, { compact: true, kicker: m.contest.city }));
    box.append(h("div", { class: "empty-state" }, icon("pin", 22), h("p", {}, "Click a city on the map, or search for one above, to see its results.")));
    return;
  }
  const city = S.cityByKey[key];
  box.append(h("div", { class: "stack" }, h("h2", { class: "panel-title" }, name),
    h("div", {}, h("a", { class: "btn small", href: hashFor("map", { contest: params.contest, precincts: params.precincts }) }, "Clear selection"))));
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
    onChange: (v) => navigate("map", { contest: v, city: params.city, precincts: params.precincts }) });
  cityBox = combobox({ label: "Find a city", placeholder: "Search cities", groups: cityOptions, value: params.city || "", emptyText: "No city with that name",
    onChange: (v) => navigate("map", { contest: params.contest, city: v, precincts: params.precincts }) });
  els.legend = h("div", {});
  els.precNote = h("span", { class: "note", role: "status" });
  els.precBtn = h("button", { class: "chip", type: "button", "aria-pressed": "false", hidden: true, onclick: () => navigate("map", { contest: params.contest, city: params.city, precincts: params.precincts === "1" ? "" : "1" }) }, icon("pin", 14), "Precincts");
  // The precinct layer is only offered when the site was built with precinct data (see sitegen/precincts.py).
  fetch("data/precincts.geojson", { method: "HEAD" }).then((r) => { if (r.ok) { els.precBtn.hidden = false; renderToolbarState(); ensurePrecincts(); } }).catch(() => {});
  els.panel = h("div", { class: "card panel", "aria-live": "polite" });
  els.mapEl = h("div", { id: "map", role: "region", "aria-label": "Map of Los Angeles County. Use the city search for a keyboard-friendly alternative." });
  els.source = S.totals ? h("button", { class: "chip map-source", type: "button", onclick: ctx.openAbout }, icon("info", 14), "About the by-city numbers") : null;
  root.replaceChildren(
    h("div", {}, h("h1", { class: "page-title" }, "Results map"), h("p", { class: "page-lede" }, "Color the map by any contest and click a city for its numbers. Countywide contests are summed from the county's precinct results.")),
    h("div", { class: "card toolbar" }, contestBox.el, cityBox.el, els.precBtn, els.precNote, h("button", { class: "btn", type: "button", onclick: () => map && fitBounds && map.fitBounds(fitBounds) }, icon("reset", 16), "Reset view")),
    h("div", { class: "map-layout" }, h("div", { class: "card map-card" }, els.mapEl, els.legend, els.source), els.panel));
  if (!S.shapes) { els.mapEl.append(h("div", { class: "empty-state" }, h("p", {}, "The city boundaries are not available right now. The city search and the results panel still work."))); return; }
  map = L.map(els.mapEl, { zoomSnap: 0.25, zoomDelta: 0.5, attributionControl: false });
  layer = L.geoJSON(S.shapes, {
    style: styleFor,
    onEachFeature: (f, lyr) => {
      lyr.bindTooltip(() => tooltipFor(f), { sticky: true });
      lyr.on("click", () => { const m = modeOf(params), k = f.properties.key; if (S.cityByKey[k] || (m.type === "cw" && m.cw.cities[k]) || k === "unincorporated") navigate("map", { contest: params.contest, city: k }); });
      lyr.on("mouseover", () => lyr.setStyle({ weight: 1.6 })); lyr.on("mouseout", () => layer.resetStyle(lyr));
    },
  }).addTo(map);
  const view = L.latLngBounds([]);
  layer.eachLayer((l) => { if (l.feature.properties.has_contests) view.extend(l.getBounds()); });
  fitBounds = view.isValid() ? view.pad(0.03) : layer.getBounds();
  window.addEventListener("themechange", () => { restyle(); renderLegend(); });
  // precinct state is not carried when switching contests unless it still applies
}

export function updateMap(root, p, ctx) {
  const first = !built;
  params = p;
  if (first) build(root, ctx);
  const m = modeOf(params);
  contestBox.set(m.value); cityBox.set(params.city || "");
  update(); ensurePrecincts();
  if (map) {
    map.invalidateSize();
    if (first) map.fitBounds(fitBounds);
    if (params.precinct && precLayer) { const lyr = precLayer.getLayers().find((l) => l.feature.properties.id === params.precinct); if (lyr) map.fitBounds(lyr.getBounds().pad(1.5), { maxZoom: 15 }); }
  }
}
