// A line chart built to the data-viz spec: 2px lines, 8px markers with a surface ring, hairline grid, a legend whenever
// there are two or more series, end-of-line labels when they fit, a crosshair tooltip that lists every series at the
// nearest tally (mouse, touch or arrow keys), and a table view with every value.
import { h, svg, countyTime } from "./util.js";

const W = 640, H = 236, T = 12, B = 32, L = 62;
const line = (c) => `stroke:${c}`;

// times: [{county_iso, county_time}]   series: [{name, color: "var(--a)", values: [number|null per tally]}]
export function lineChart({ times, series, format, label }) {
  const wrap = h("div", { class: "chart-wrap" });
  const direct = series.length >= 2 && series.length <= 4;
  const R = direct ? 118 : 18;
  const all = series.flatMap((s) => s.values.filter((v) => v !== null));
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart", role: "img", tabindex: "0", "aria-label": label });
  wrap.append(root);
  if (all.length === 0) return wrap;

  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi - lo < 1e-9) { const pad = Math.abs(lo) * 0.05 + 0.01; lo -= pad; hi += pad; }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const stamps = times.map((t) => Date.parse(t.county_iso));
  const byTime = stamps.every((s) => !isNaN(s)) && stamps[stamps.length - 1] > stamps[0];
  const xs = times.map((_, i) => L + (times.length === 1 ? 0.5 : byTime ? (stamps[i] - stamps[0]) / (stamps[stamps.length - 1] - stamps[0]) : i / (times.length - 1)) * (W - L - R));
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);

  for (let k = 0; k <= 3; k++) {
    const v = lo + ((hi - lo) * k) / 3, yy = y(v);
    root.append(svg("line", { x1: L, x2: W - R, y1: yy, y2: yy, class: "grid" }));
    const t = svg("text", { x: L - 8, y: yy + 4, "text-anchor": "end" }); t.textContent = format(v); root.append(t);
  }
  [0, times.length - 1].forEach((i, n) => {
    if (n === 1 && i === 0) return;
    const t = svg("text", { x: xs[i], y: H - 10, "text-anchor": times.length === 1 ? "middle" : n === 0 ? "start" : "end" });
    t.textContent = countyTime(times[i].county_time); root.append(t);
  });

  const showDots = times.length <= 40;
  series.forEach((s) => {
    const pts = s.values.map((v, i) => (v === null ? null : [xs[i], y(v)])).filter(Boolean);
    if (pts.length > 1) root.append(svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", style: line(s.color), "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    (showDots ? pts : pts.slice(-1)).forEach((p) => root.append(svg("circle", { cx: p[0], cy: p[1], r: 4, style: `fill:${s.color};stroke:var(--surface)`, "stroke-width": 2 })));
  });

  if (direct) { // end-of-line labels, only when they do not collide
    const ends = series.map((s) => { const i = s.values.map((v) => v !== null).lastIndexOf(true); return i < 0 ? null : { s, x: xs[i], y: y(s.values[i]) }; }).filter(Boolean).sort((a, b) => a.y - b.y);
    if (ends.every((e, i) => i === 0 || e.y - ends[i - 1].y >= 14)) {
      ends.forEach((e) => { const t = svg("text", { x: e.x + 10, y: e.y + 4, style: "fill:var(--text-2)", "font-weight": 600 }); t.textContent = e.s.name.length > 17 ? e.s.name.slice(0, 16) + "…" : e.s.name; root.append(t); });
    }
  }

  // ---- hover layer: crosshair, highlighted markers, one tooltip listing every series -----------------------------------
  const cross = svg("line", { class: "cross", y1: T, y2: H - B, visibility: "hidden" });
  const marks = series.map((s) => svg("circle", { r: 5.5, style: `fill:${s.color};stroke:var(--surface)`, "stroke-width": 2, visibility: "hidden" }));
  const hit = svg("rect", { x: L - 6, y: 0, width: W - L - R + 12, height: H - B + 6, fill: "transparent" });
  root.append(cross, ...marks, hit);
  const tip = h("div", { class: "tip", hidden: true, role: "status" });
  wrap.append(tip);
  let current = -1;
  function show(i) {
    current = i;
    cross.setAttribute("x1", xs[i]); cross.setAttribute("x2", xs[i]); cross.setAttribute("visibility", "visible");
    marks.forEach((m, k) => { const v = series[k].values[i]; if (v === null) m.setAttribute("visibility", "hidden"); else { m.setAttribute("cx", xs[i]); m.setAttribute("cy", y(v)); m.setAttribute("visibility", "visible"); } });
    tip.replaceChildren(h("div", { class: "tip-head" }, countyTime(times[i].county_time)),
      ...series.map((s) => h("div", { class: "tip-row" }, h("span", { class: "line-key", style: { borderColor: s.color } }), h("span", { class: "muted" }, s.name), h("b", {}, s.values[i] === null ? "–" : format(s.values[i], true)))));
    tip.hidden = false;
    const scale = wrap.clientWidth / W, left = xs[i] * scale, flip = left > wrap.clientWidth * 0.6;
    tip.style.left = flip ? "auto" : `${left + 14}px`; tip.style.right = flip ? `${wrap.clientWidth - left + 14}px` : "auto"; tip.style.top = "8px";
  }
  function hide() { current = -1; cross.setAttribute("visibility", "hidden"); marks.forEach((m) => m.setAttribute("visibility", "hidden")); tip.hidden = true; }
  const nearest = (clientX) => { const r = root.getBoundingClientRect(), x = ((clientX - r.left) / r.width) * W; return xs.reduce((b, v, i) => (Math.abs(v - x) < Math.abs(xs[b] - x) ? i : b), 0); };
  hit.addEventListener("pointermove", (e) => show(nearest(e.clientX)));
  hit.addEventListener("pointerdown", (e) => show(nearest(e.clientX)));
  root.addEventListener("pointerleave", hide);
  root.addEventListener("blur", hide);
  root.addEventListener("focus", () => show(times.length - 1));
  root.addEventListener("keydown", (e) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); show(Math.max(0, Math.min(times.length - 1, (current < 0 ? times.length - 1 : current) + (e.key === "ArrowLeft" ? -1 : 1)))); }
    else if (e.key === "Escape") hide();
  });

  if (series.length >= 2) {
    wrap.append(h("div", { class: "chart-legend" }, series.map((s) => h("span", {}, h("span", { class: "line-key", style: { borderColor: s.color } }), s.name))));
  }
  // table view: every value, reachable without hovering
  const rows = times.map((t, i) => [countyTime(t.county_time), ...series.map((s) => (s.values[i] === null ? "–" : format(s.values[i], true)))]).slice(-12).reverse();
  wrap.append(h("details", { class: "more", style: { marginTop: "10px" } }, h("summary", {}, "Table view"),
    h("table", { class: "data" }, h("thead", {}, h("tr", {}, h("th", {}, "Tally (county time)"), ...series.map((s) => h("th", {}, s.name)))),
      h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))))));
  return wrap;
}
