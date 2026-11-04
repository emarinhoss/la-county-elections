// Draws the map and the results panel from two files:
//   data/city_contests.json       results per city (always present)
//   data/city_boundaries.geojson  city shapes (may be missing; the city list still works)
// Text is added with textContent (never innerHTML) so county text can never inject markup.

const BLUE = "#1f6fb2", ORANGE = "#d9822b", GREY = "#c9ced6";
let map, layer, cityView, data, selectedKey = null, colorContestId = "";
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
function featureColor(props) {
  const city = byKey[props.key];
  if (!city) return GREY;
  if (colorContestId) {
    const c = city.contests.find((x) => String(x.id) === colorContestId);
    return c ? contestColor(c) : GREY;
  }
  return shade(BLUE, 0.35 + 0.65 * Math.min(city.contests.length / 6, 1));
}
function style(feature) {
  const p = feature.properties, picked = p.key === selectedKey;
  return { fillColor: featureColor(p), fillOpacity: p.has_contests ? 0.9 : 0.35,
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
  const c = Object.values(byKey).flatMap((x) => x.contests).find((x) => String(x.id) === colorContestId);
  if (c && c.kind === "measure") { add(BLUE, "YES leads"); add(ORANGE, "NO leads"); add(GREY, "Other cities"); }
  else { add(BLUE, "Leader's share (darker = larger)"); add(GREY, "Other cities"); }
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
  return box;
}
function showCity(key) {
  selectedKey = key;
  document.getElementById("city-select").value = key || "";
  const panel = document.getElementById("contests");
  panel.replaceChildren();
  const city = byKey[key];
  if (!city) { panel.append(el("p", "muted", "Choose a city on the map or from the list.")); }
  else {
    panel.append(el("h2", null, city.name));
    city.contests.forEach((c) => panel.append(renderContest(c)));
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
  cSel.addEventListener("change", () => {
    colorContestId = cSel.value;
    const owner = data.cities.find((city) => city.contests.some((c) => String(c.id) === colorContestId));
    if (owner) showCity(owner.key); else if (layer) layer.setStyle(style);
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
      lyr.on("click", () => { if (byKey[f.properties.key]) showCity(f.properties.key); });
    },
  }).addTo(map);
  // Fit the view to cities that have contests, so remote areas and offshore islands do not shrink the map.
  const view = L.latLngBounds([]);
  layer.eachLayer((l) => { if (l.feature.properties.has_contests) view.extend(l.getBounds()); });
  cityView = view.isValid() ? view.pad(0.03) : layer.getBounds();
  map.fitBounds(cityView);
}
start().catch((e) => { document.getElementById("status").textContent = "Could not load data: " + e.message; });
