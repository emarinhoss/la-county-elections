// Starts the site: loads data, routes between the three views, and wires up the header.
import { h, utcStamp, countyTime, plural } from "./util.js";
import { S, load } from "./store.js";
import { parseHash } from "./router.js";
import { renderOverview } from "./overview.js";
import { updateMap } from "./mapview.js";
import { updateContests } from "./contests.js";

const $ = (id) => document.getElementById(id);
const VIEWS = ["overview", "map", "contests"];
const about = $("about");
const openAbout = () => { buildAbout(); if (!about.open) about.showModal(); };
const ctx = { openAbout };
let overviewDrawn = false;

function buildAbout() {
  const body = $("about-body"), t = (S.totals && S.totals.tally) || {};
  const p = (...kids) => h("p", {}, ...kids);
  body.replaceChildren(
    h("h3", {}, "Unofficial results"), p("The numbers come from the Los Angeles County Registrar-Recorder/County Clerk's public results files. They are partial and unofficial. They change as more ballots are counted, until the county certifies the election."),
    h("h3", {}, "What “tally” means"), p(`Each time the county posts new results it is one tally. This page shows the latest one we saved${S.city ? " (" + countyTime(S.city.county_time) + ", county time)" : ""}. Times are the county's clock, not ours.`),
    h("h3", {}, "Results by city"),
    p(S.totals ? "Countywide contests are not published by city. We add up the county's precinct-level Statement of Votes Cast and assign each precinct to the city whose boundary covers most of it, or to unincorporated areas." : "The county has not yet published the precinct-level file needed to total countywide contests by city."),
    S.totals ? p(`${t.is_latest === false ? "These city numbers are from an older tally than the live county totals" : "These city numbers match the latest county tally"}` + (t.largest_difference ? `; every contest total is within ${(t.largest_difference * 100).toFixed(2)}% of the county's tally.` : ".") + " Some ballots may be placed by place name when no precinct shape could be found; the map panel says when that happens.") : null,
    h("h3", {}, "Open data"), p("Everything shown was fetched from public sources and recorded in ", h("a", { href: "https://github.com/emarinhoss/la-county-elections" }, "this open repository"), "."));
}

function setNav(view) {
  document.querySelectorAll("[data-nav]").forEach((a) => (a.dataset.nav === view ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
}
function route() {
  let { view, params } = parseHash();
  if (!VIEWS.includes(view)) view = "overview";
  VIEWS.forEach((v) => ($("view-" + v).hidden = v !== view));
  setNav(view);
  if (!S.city) return;
  if (view === "overview" && !overviewDrawn) { overviewDrawn = true; renderOverview($("view-overview"), ctx); }
  if (view === "map") updateMap($("view-map"), params, ctx);
  if (view === "contests") updateContests($("view-contests"), params);
  const titles = { overview: "Overview", map: "Results map", contests: "All contests" };
  document.title = `${titles[view]} · LA County Election Results`;
  if (!route.first) { route.first = true; return; }
  window.scrollTo({ top: 0 });
}

function setStatus() {
  const chip = $("status-chip"), t = S.city.county_time;
  $("status-text").replaceChildren(h("span", { class: "long" }, "Tally "), countyTime(t));
  chip.title = "County tally time (county clock). " + (S.city.built_at ? `Page built ${utcStamp(S.city.built_at)}.` : "");
  $("brand-sub").textContent = S.city.election.title;
}

function setupTheme() {
  const root = document.documentElement;
  $("theme-btn").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch (e) {}
    window.dispatchEvent(new Event("themechange"));
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => window.dispatchEvent(new Event("themechange")));
}

$("about-btn").addEventListener("click", openAbout);
$("about-close").addEventListener("click", () => about.close());
about.addEventListener("click", (e) => { if (e.target === about) about.close(); });
setupTheme();
window.addEventListener("hashchange", route);
setNav(parseHash().view);

load().then(() => { setStatus(); route(); }).catch((e) => {
  $("status-text").textContent = "Could not load";
  $("view-overview").hidden = false;
  $("view-overview").replaceChildren(h("div", { class: "card pad" }, h("h1", { class: "page-title" }, "The results could not be loaded"), h("p", { class: "page-lede" }, `${e.message}. Try reloading the page in a minute.`)));
});
