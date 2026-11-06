// Small helpers shared by every view. Text is always added as text nodes (never innerHTML), so county-supplied
// names and measure text can never inject markup.

export function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return e;
}
export function svg(tag, attrs = {}, ...kids) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) e.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid) e.append(kid);
  return e;
}

// Icons are fixed markup written here, never built from data.
const ICONS = { info: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>', search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>', pin: '<path d="M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>', reset: '<path d="M4 4v5h5"/><path d="M5.5 15a7 7 0 101.8-7.3L4 9"/>' };
export function icon(name, size = 18) {
  const e = svg("svg", { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
  e.innerHTML = ICONS[name] || "";
  return e;
}

// ---- formatting ---------------------------------------------------------------------------------------------------
export const num = (x) => (x === null || x === undefined ? "–" : Math.round(x).toLocaleString("en-US"));
export const pct = (x, digits = 1) => (x === null || x === undefined ? "–" : (x * 100).toFixed(digits) + "%");
export function compact(x) {
  if (x === null || x === undefined) return "–";
  if (x >= 1e6) return (x / 1e6).toFixed(x >= 1e7 ? 0 : 1).replace(/\.0$/, "") + "M";
  if (x >= 1e4) return Math.round(x / 1e3) + "K";
  return Math.round(x).toLocaleString("en-US");
}
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// County times look like "11/4/2026 4:28:25 PM" and carry no time zone, so we reformat the text and never convert it.
export function countyTime(text) {
  const m = /^(\d+)\/(\d+)\/\d+ (\d+):(\d+):\d+ (AM|PM)$/.exec(text || "");
  return m ? `${MONTHS[+m[1] - 1]} ${+m[2]}, ${+m[3]}:${m[4]} ${m[5]}` : text || "";
}
export function utcStamp(iso) {
  const d = new Date(iso);
  return isNaN(d) ? "" : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}
export const plural = (n, one, many) => `${num(n)} ${n === 1 ? one : many || one + "s"}`;
const SMALL = new Set(["of", "the", "and", "for", "to", "in", "or"]);
export const titleCase = (s) => (s === s.toUpperCase()
  ? s.toLowerCase().replace(/\b[a-z]+/g, (w, at) => (at > 0 && SMALL.has(w) ? w : w[0].toUpperCase() + w.slice(1)))
  : s);

// ---- colors ---------------------------------------------------------------------------------------------------------
// The palette lives in CSS custom properties (light and dark are separate selected steps). Colors that the map and the
// charts need as concrete values are read from CSS at draw time, so a theme switch just redraws.
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export function palette() {
  return { a: cssVar("--a"), b: cssVar("--b"), other: cssVar("--other"), mid: cssVar("--div-mid"), nodata: cssVar("--nodata"),
           line: cssVar("--map-line"), seqLo: cssVar("--seq-lo"), seqHi: cssVar("--seq-hi"), text: cssVar("--text"), surface: cssVar("--surface"),
           series: ["--a", "--b", "--c3", "--c4", "--c5", "--c6"].map(cssVar) };
}
function rgb(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [128, 128, 128];
}
export function mix(hexA, hexB, t) { // t = 0 gives A, t = 1 gives B
  const a = rgb(hexA), b = rgb(hexB), c = a.map((v, i) => Math.round(v + (b[i] - v) * Math.max(0, Math.min(1, t))));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
// Diverging scale: neutral gray at a 50-50 split, one hue per side, equal steps per arm. Reaches the full hue at a 30 point lead.
export function diverging(share, P, span = 0.3) {
  const d = Math.max(-1, Math.min(1, (share - 0.5) / span));
  return d >= 0 ? mix(P.mid, P.a, d) : mix(P.mid, P.b, -d);
}

// Who is shown in blue and who in orange never depends on a city's own numbers (color follows the choice, not its rank):
// a measure is YES blue / NO orange; with two candidates the county-wide leader is blue; with more, only the leader is accented.
export function leaderIndex(choices) {
  const v = (c) => (c.county_votes !== undefined ? c.county_votes : c.votes);
  return choices.reduce((best, c, i) => (v(c) > v(choices[best]) ? i : best), 0);
}
export function choiceColor(contest, i) {
  const names = contest.choices.map((c) => c.name.toUpperCase());
  if (contest.kind === "measure" && names.includes("YES") && names.includes("NO")) return names[i] === "YES" ? "var(--a)" : names[i] === "NO" ? "var(--b)" : "var(--other)";
  const lead = leaderIndex(contest.choices);
  if (contest.choices.length === 2) return i === lead ? "var(--a)" : "var(--b)";
  return i === lead ? "var(--a)" : "var(--other)";
}

export async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
