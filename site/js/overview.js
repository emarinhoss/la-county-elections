// The landing view: the headline numbers, the races most people look for, and a way into everything else.
import { h, num, pct, countyTime, icon } from "./util.js";
import { S, getHistory } from "./store.js";
import { contestCard, meter, segmentedBar } from "./components.js";
import { lineChart } from "./chart.js";
import { TOPICS, topicOf } from "./topics.js";

const FEATURED = ["GOVERNOR", "SHERIFF", "COUNTY MEASURE A", "COUNTY MEASURE E"];
const prettyDate = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" }); };

export function renderOverview(root, ctx) {
  root.replaceChildren();
  const t = S.county && S.county.totals;
  root.append(h("div", {}, h("h1", { class: "page-title" }, "Los Angeles County election results"),
    h("p", { class: "page-lede" }, `${S.city.election.title}, ${prettyDate(S.city.election.date)}. Results are unofficial and the count is still going: numbers change until the county certifies the election.`)));

  root.append(h("div", { class: "callout", role: "note" }, icon("info"),
    h("div", {}, "These are partial, unofficial counts from the county. ", h("button", { type: "button", onclick: ctx.openAbout }, "How to read these numbers"), ".")));

  if (t) {
    const inPerson = Math.max(0, t.ballots_counted - t.vote_by_mail_ballots);
    root.append(h("section", { class: "card hero", "aria-label": "Ballots counted" },
      h("div", { class: "hero-main" },
        h("p", { class: "eyebrow" }, "Ballots counted so far"),
        h("p", { class: "hero-number num" }, num(t.ballots_counted)),
        h("p", { class: "hero-sub" }, `${pct(t.share_of_registered)} of ${num(t.registered)} registered voters`),
        meter(t.share_of_registered, "Share of registered voters whose ballot is counted"),
        h("div", { class: "meter-labels" }, h("span", {}, "0%"), h("span", {}, "Ballots still arriving are not in this number"), h("span", {}, "100%"))),
      h("div", { class: "hero-side" },
        h("h2", { class: "section-title", style: { fontSize: "15px" } }, "How the counted ballots were cast"),
        segmentedBar([{ name: "Vote by mail", value: t.vote_by_mail_ballots, color: "var(--a)" }, { name: "In person and other", value: inPerson, color: "var(--c3)" }], "Counted ballots by how they were cast"),
        h("p", { class: "note" }, `Count as of ${countyTime(S.city.county_time)} (county time).`))));
  }

  // key races
  const featured = FEATURED.map((label) => S.countyList.find((c) => c.label.toUpperCase() === label)).filter(Boolean);
  const la = S.cityByKey.losangeles && S.cityByKey.losangeles.contests.find((c) => c.label === "Mayor");
  if (featured.length || la) {
    root.append(h("div", { class: "stack" },
      h("h2", { class: "section-title" }, "Key races", h("small", {}, "the contests most people look for")),
      h("div", { class: "grid-2" }, featured.map((c) => contestCard(c, { kind: "county", compact: true, kicker: topicOf(c.group) === "county" ? "County" : "Statewide" })),
        la && contestCard(la, { kind: "city", compact: true, kicker: "City of Los Angeles" }))));
  }

  // ballots over time
  const over = h("div", { class: "card pad stack" }, h("h2", { class: "section-title", style: { fontSize: "15px" } }, "Ballots counted over time"), h("p", { class: "note" }, "Loading…"));
  root.append(over);
  getHistory().then((hist) => {
    over.replaceChildren(h("h2", { class: "section-title", style: { fontSize: "15px" } }, "Ballots counted over time"),
      lineChart({ times: hist.times, series: [{ name: "Ballots counted", color: "var(--a)", values: hist.ballots_counted }], format: (v) => Math.round(v).toLocaleString("en-US"), label: "Ballots counted over time" }),
      hist.times.length < 3 ? h("p", { class: "note" }, `Only ${hist.times.length === 1 ? "one tally has" : hist.times.length + " tallies have"} been saved so far. This fills in as the county posts updates.`) : null);
  }).catch(() => over.remove());

  // browse
  const counts = {};
  for (const c of S.countyList) counts[topicOf(c.group)] = (counts[topicOf(c.group)] || 0) + 1;
  counts.cities = S.cityContests.length;
  root.append(h("div", { class: "stack" },
    h("h2", { class: "section-title" }, "Browse every contest", h("small", {}, `${num(S.countyList.length + S.cityContests.length)} on this ballot`)),
    h("div", { class: "tiles" }, TOPICS.filter((tp) => counts[tp.id]).map((tp) =>
      h("a", { class: "tile", href: `#/contests?topic=${tp.id}` }, h("span", { class: "n num" }, num(counts[tp.id])), h("b", {}, tp.label), h("span", {}, tp.blurb)))),
    h("div", {}, h("a", { class: "btn primary", href: "#/map" }, "Explore the map"))));
}
