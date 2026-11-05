// The "All contests" view: search, filter by topic, read the cards.
import { h, num, icon, titleCase } from "./util.js";
import { S } from "./store.js";
import { contestCard } from "./components.js";
import { TOPICS, topicOf } from "./topics.js";
import { navigate } from "./router.js";

const PAGE = 12;   // cards shown per section before "Show more"
let built = false, els = {}, params = {}, expanded = new Set();

function entries() { // every contest as {topic, kind, contest, text}
  const out = [];
  for (const c of S.countyList) out.push({ topic: topicOf(c.group), kind: "county", contest: c, kicker: c.group });
  for (const c of S.cityContests) out.push({ topic: "cities", kind: "city", contest: c, kicker: c.city });
  for (const e of out) e.text = [e.contest.label, e.kicker, ...e.contest.choices.map((x) => x.name)].join(" ").toLowerCase();
  return out;
}
let all = [];

function draw() {
  const q = (params.q || "").trim().toLowerCase(), topic = params.topic || "";
  const words = q.split(/\s+/).filter(Boolean);
  const matches = all.filter((e) => words.every((w) => e.text.includes(w)));
  // chips show how many contests each topic has for the current search
  const counts = {};
  for (const e of matches) counts[e.topic] = (counts[e.topic] || 0) + 1;
  els.chips.replaceChildren(
    h("button", { class: "chip", type: "button", "aria-pressed": String(!topic), onclick: () => go({ topic: "" }) }, "All", h("span", { class: "count" }, num(matches.length))),
    ...[...TOPICS, { id: "other", label: "Other" }].filter((t) => counts[t.id]).map((t) =>
      h("button", { class: "chip", type: "button", "aria-pressed": String(topic === t.id), onclick: () => go({ topic: t.id }) }, t.label, h("span", { class: "count" }, num(counts[t.id])))));
  const shown = topic ? matches.filter((e) => e.topic === topic) : matches;
  els.result.replaceChildren();
  els.count.textContent = `${num(shown.length)} contest${shown.length === 1 ? "" : "s"}` + (q ? ` matching “${params.q}”` : "");
  if (!shown.length) {
    els.result.append(h("div", { class: "empty-state" }, icon("search", 22), h("p", {}, q ? "No contest matches that search." : "No contests here."),
      q ? h("button", { class: "btn small", type: "button", onclick: () => go({ q: "", topic: "" }) }, "Clear search") : null));
    return;
  }
  for (const t of [...TOPICS, { id: "other", label: "Other", blurb: "" }]) {
    const rows = shown.filter((e) => e.topic === t.id);
    if (!rows.length) continue;
    const open = expanded.has(t.id) || !!q || !!topic;
    const list = open ? rows : rows.slice(0, PAGE);
    els.result.append(h("section", { class: "stack", "aria-label": t.label },
      h("h2", { class: "section-title" }, t.label, h("small", {}, String(rows.length))),
      h("div", { class: "grid-2" }, list.map((e) => contestCard(e.contest, { kind: e.kind, kicker: titleCase(e.kicker) === titleCase(e.contest.label) ? "" : titleCase(e.kicker) }))),
      rows.length > list.length ? h("div", {}, h("button", { class: "btn", type: "button", onclick: () => { expanded.add(t.id); draw(); } }, `Show all ${rows.length}`)) : null));
  }
}

function go(change) { navigate("contests", { topic: params.topic, q: params.q, ...change }, { replace: true }); }

export function updateContests(root, p) {
  params = p;
  if (!built) {
    built = true; all = entries();
    els.input = h("input", { type: "search", placeholder: "Search by race, measure, candidate or city", "aria-label": "Search contests", autocomplete: "off" });
    let timer;
    els.input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => go({ q: els.input.value }), 150); });
    els.chips = h("div", { class: "chips", role: "group", "aria-label": "Filter by topic" });
    els.count = h("p", { class: "note", role: "status" });
    els.result = h("div", { class: "stack", style: { gap: "28px" } });
    root.replaceChildren(
      h("div", {}, h("h1", { class: "page-title" }, "All contests"), h("p", { class: "page-lede" }, "Every race and measure the county has reported, from statewide offices to city councils.")),
      h("div", { class: "stack" }, h("div", { class: "search" }, icon("search", 18), els.input), els.chips, els.count), els.result);
  }
  if (document.activeElement !== els.input) els.input.value = p.q || "";
  draw();
}
