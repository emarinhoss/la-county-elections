// Pieces used by more than one view: result rows, the contest card, the searchable picker, meter and segmented bar.
import { h, num, pct, titleCase, choiceColor, countyTime } from "./util.js";
import { lineChart } from "./chart.js";
import { S, getHistory } from "./store.js";

// ---- result rows -----------------------------------------------------------------------------------------------------------
// items: [{name, party, votes, share, color}] in any order. The leader gets the accent; a row never relies on color alone:
// every row prints its share and its votes, and the leader says "Leading".
export function resultRows(items) {
  const sorted = [...items].sort((a, b) => b.votes - a.votes);
  const lead = sorted.length > 1 && sorted[0].votes > sorted[1].votes ? sorted[0] : sorted.length === 1 && sorted[0].votes > 0 ? sorted[0] : null;
  return h("div", { class: "rows" }, sorted.map((it) => {
    const party = it.party && it.party !== "Non Partisan" ? it.party : "";
    return h("div", { class: "row" },
      h("div", { class: "row-top" },
        h("span", { class: "row-name" }, it.name, party && h("small", {}, party), it === lead && h("span", { class: "row-lead" }, "Leading")),
        h("span", { class: "num" }, h("span", { class: "row-share" }, pct(it.share)), h("span", { class: "row-votes" }, num(it.votes)))),
      h("div", { class: "bar", "aria-hidden": "true" }, h("span", { style: { width: `${(it.share || 0) * 100}%`, background: it.color } })));
  }));
}
export const itemsOf = (contest) => contest.choices.map((c, i) => ({ name: c.name, party: c.party, votes: c.votes, share: c.share, color: choiceColor(contest, i) }));

// ---- a details block whose body is built the first time it is opened ------------------------------------------------------
export function lazyDetails(summary, build) {
  const d = h("details", { class: "more" }, h("summary", {}, summary));
  const body = h("div", { class: "more-body" });
  d.append(body);
  d.addEventListener("toggle", () => { if (d.open && !d.dataset.built) { d.dataset.built = "1"; build(body); } });
  return d;
}

// ---- how the count changed (share of votes per choice, one point per saved county tally) ------------------------------------
function historyBody(contest) {
  return (body) => {
    body.append(h("p", { class: "note" }, "Loading…"));
    getHistory().then((hist) => {
      body.replaceChildren();
      const hc = hist.contests[String(contest.id)];
      if (!hc) { body.append(h("p", { class: "note" }, "No history was saved for this contest.")); return; }
      const n = hist.times.length;
      const totals = hist.times.map((_, i) => hc.choices.reduce((s, c) => s + (c.votes[i] || 0), 0));
      const order = hc.choices.map((c, i) => i).sort((a, b) => (hc.choices[b].votes[n - 1] || 0) - (hc.choices[a].votes[n - 1] || 0)).slice(0, 6);
      const SLOT = ["var(--a)", "var(--b)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)"];
      const series = order.map((i) => {
        const c = hc.choices[i];
        const color = hc.choices.length === 2 ? choiceColor(contest, contest.choices.findIndex((x) => x.name === c.name)) : SLOT[Math.min(i, 5)];   // color follows the choice, not its rank
        return { name: c.name, color, values: c.votes.map((v, k) => (v === null || totals[k] === 0 ? null : v / totals[k])) };
      });
      body.append(lineChart({ times: hist.times, series, format: (v, precise) => pct(v, precise ? 2 : 0),
        label: `Share of votes over ${n} tally${n === 1 ? "" : "s"}: ` + series.map((s) => `${s.name} ${pct(s.values[n - 1])}`).join(", ") }));
      if (n < 3) body.append(h("p", { class: "note", style: { marginTop: "8px" } }, `Only ${n === 1 ? "one tally has" : n + " tallies have"} been saved so far. Earlier election-night tallies were published before this site started saving them; the chart fills in as the county posts updates.`));
    }).catch((e) => { body.replaceChildren(h("p", { class: "note" }, "The history could not be loaded: " + e.message)); });
  };
}

// ---- contest card -----------------------------------------------------------------------------------------------------------
// contest: {id, label, kind, vote_for, pass_rate, ballots_cast, choices:[{name, party, votes, share}], measure_text?}
export function contestCard(contest, o = {}) {
  const meta = [contest.kind === "measure" ? "Ballot measure" : contest.kind === "judicial" ? "Judicial" : "Candidate race"];
  if (contest.vote_for > 1) meta.push(`Vote for up to ${contest.vote_for}`);
  if (contest.kind === "measure" && contest.pass_rate) meta.push(`Passes with: ${contest.pass_rate.toLowerCase()}`);
  if (contest.ballots_cast) meta.push(`${num(contest.ballots_cast)} ballots counted`);
  const card = h("article", { class: "card contest" },
    h("div", { class: "contest-head" }, o.kicker && h("span", { class: "tag" }, o.kicker), h("h3", { class: "contest-title" }, titleCase(contest.label)), h("div", { class: "contest-meta" }, meta.map((m) => h("span", {}, m)))),
    resultRows(itemsOf(contest)));
  const foot = h("div", { class: "contest-foot" });
  const cw = o.kind === "county" && S.cwById[contest.id];
  if (cw) foot.append(h("a", { class: "btn small", href: `#/map?contest=cw:${contest.id}` }, "See results by city"));
  if (o.kind === "city") foot.append(h("a", { class: "btn small", href: `#/map?city=${contest.cityKey}` }, "Show on map"));
  if (foot.childNodes.length) card.append(foot);
  if (!o.compact) {
    if (contest.measure_text) card.append(h("details", { class: "more" }, h("summary", {}, "Read the measure"), h("div", { class: "more-body measure-text" }, contest.measure_text)));
    card.append(lazyDetails("How the count changed", historyBody(contest)));
  }
  return card;
}

// ---- meter and segmented bar (see the data-viz spec) -------------------------------------------------------------------------
export const meter = (value, label) => h("div", {}, h("div", { class: "meter", role: "meter", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": Math.round(value * 100), "aria-label": label }, h("span", { style: { width: `${Math.max(0, Math.min(1, value)) * 100}%` } })));
export function segmentedBar(parts, label) { // parts: [{name, value, color}] -> thin bar + a legend that names every part with its amount and share
  const total = parts.reduce((s, p) => s + p.value, 0) || 1;
  return h("div", { class: "stack" },
    h("div", { class: "segbar", role: "img", "aria-label": label + ": " + parts.map((p) => `${p.name} ${pct(p.value / total, 0)}`).join(", ") },
      parts.filter((p) => p.value > 0).map((p) => h("span", { style: { width: `${(p.value / total) * 100}%`, background: p.color } }))),
    h("div", { class: "legend-list" }, parts.map((p) => h("div", { class: "legend-row" }, h("span", { class: "key", style: { background: p.color } }), h("span", {}, p.name), h("span", {}, h("b", {}, num(p.value)), h("span", { class: "muted" }, pct(p.value / total, 0)))))));
}

// ---- searchable picker (combobox) ---------------------------------------------------------------------------------------------
// groups(): [{label, options: [{value, label, disabled?}]}]. Type to filter; arrow keys and Enter work; Escape restores.
let comboCount = 0;
export function combobox({ label, placeholder, groups, value = "", onChange, emptyText = "Nothing matches" }) {
  const id = "combo" + ++comboCount;
  const input = h("input", { id, type: "text", role: "combobox", autocomplete: "off", "aria-autocomplete": "list", "aria-expanded": "false", "aria-controls": id + "-list", placeholder });
  const list = h("ul", { id: id + "-list", role: "listbox", "aria-label": label, hidden: true });
  const root = h("div", { class: "field" }, h("label", { for: id }, label), h("div", { class: "combo" }, input, h("span", { class: "chev", "aria-hidden": "true" }), list));
  let current = value, shown = [], active = -1;
  const all = () => groups().flatMap((g) => g.options);
  const labelOf = (v) => (all().find((o) => o.value === v) || {}).label || "";
  const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); input.value = labelOf(current); };
  function render(query) {
    const q = query.trim().toLowerCase();
    list.replaceChildren(); shown = [];
    for (const g of groups()) {
      const opts = g.options.filter((o) => !q || o.label.toLowerCase().includes(q) || g.label.toLowerCase().includes(q));
      if (!opts.length) continue;
      if (g.label) list.append(h("li", { role: "presentation" }, g.label));
      for (const o of opts) {
        const li = h("li", { role: "option", id: `${id}-o${shown.length}`, "aria-selected": "false", "aria-disabled": o.disabled ? "true" : null, "data-index": shown.length });
        const at = q ? o.label.toLowerCase().indexOf(q) : -1;
        if (at >= 0) li.append(o.label.slice(0, at), h("mark", {}, o.label.slice(at, at + q.length)), o.label.slice(at + q.length)); else li.append(o.label);
        list.append(li); shown.push(o);
      }
    }
    if (!shown.length) list.append(h("li", { class: "empty", role: "presentation" }, emptyText));
    setActive(shown.findIndex((o) => o.value === current && !q));
  }
  function setActive(i) {
    active = i;
    list.querySelectorAll('[role="option"]').forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
    if (i >= 0) { const li = list.querySelector(`#${id}-o${i}`); input.setAttribute("aria-activedescendant", li.id); li.scrollIntoView({ block: "nearest" }); } else input.removeAttribute("aria-activedescendant");
  }
  function open() { list.hidden = false; input.setAttribute("aria-expanded", "true"); render(""); }
  function choose(o) { if (!o || o.disabled) return; current = o.value; close(); onChange(o.value); }
  input.addEventListener("focus", () => { input.select(); open(); });
  input.addEventListener("click", () => { if (list.hidden) open(); });
  input.addEventListener("input", () => { list.hidden = false; input.setAttribute("aria-expanded", "true"); render(input.value); if (shown.length) setActive(0); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (list.hidden) open(); else setActive(Math.min(shown.length - 1, active + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(Math.max(0, active - 1)); }
    else if (e.key === "Enter") { if (!list.hidden) { e.preventDefault(); choose(shown[active]); } }
    else if (e.key === "Escape") { close(); }
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
  list.addEventListener("mousedown", (e) => { e.preventDefault(); const li = e.target.closest('[role="option"]'); if (li) choose(shown[+li.dataset.index]); });
  input.value = labelOf(current);
  return { el: root, set(v) { current = v; if (document.activeElement !== input) input.value = labelOf(v); }, refresh() { input.value = labelOf(current); } };
}
export { countyTime };
