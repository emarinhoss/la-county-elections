import { turnoutByPrecinct, turnoutOf, extremes, scale } from "../../site/js/analysis.js";
import assert from "node:assert/strict";
const prec = { votes: {
  A: { city: "x", v: { 1: [1000, 400, 1, 1], 2: [1000, 450, 1, 1], 99: [1000, 999, 1] } },   // 99 is not countywide: ignored; max of 400, 450
  B: { city: "y", v: { 1: [600, 300, 1, 1] } },
  C: { city: "x", v: { 1: [0, 0, 0, 0] } },                                                    // no registered voters: rate null
  D: { city: "x", v: { 99: [10, 5] } } } };                                                    // no countywide contest at all: skipped
const t = turnoutByPrecinct(prec, [1, 2]);
assert.equal(t.rows.size, 3); assert.equal(t.rows.get("A").ballots, 450); assert.equal(t.rows.get("A").rate, 0.45); assert.equal(t.rows.get("C").rate, null);
assert.equal(t.reg, 1600); assert.equal(t.ballots, 750);
assert.deepEqual(turnoutOf(t, (x) => x.city === "x"), { reg: 1000, ballots: 450, n: 2, rate: 0.45 });
const e = extremes(t, 1); assert.equal(e.highest[0].id, "B"); assert.equal(e.lowest[0].id, "A"); assert.equal(e.eligible, 2);   // C excluded (rate null)
assert.equal(scale(0.5, 0.2, 0.6), 0.75); assert.equal(scale(0.9, 0.2, 0.6), 1); assert.equal(scale(0.1, 0.2, 0.6), 0); assert.equal(scale(0.3, 0.3, 0.3), 0.5);
console.log("analysis tests pass");
