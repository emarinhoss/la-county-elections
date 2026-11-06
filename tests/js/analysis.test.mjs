import { turnoutByPrecinct, turnoutOf, extremes, scale, methodSplit, shareOf, inPersonMinusMail, vbmShareByPrecinct, vbmOf } from "../../site/js/analysis.js";
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
// vote by mail versus in person
const sp = methodSplit([1000, 500, 300, 200], [350, 240, 110]);     // 500 ballots, 350 by mail: 150 in person; choice 0: 300 total, 240 by mail, 60 in person
assert.deepEqual(sp.ip, [60, 90]); assert.deepEqual(sp.ballots, { all: 500, vbm: 350, ip: 150 });
assert.equal(shareOf(sp.vbm, 0), 240 / 350); assert.equal(shareOf([0, 0], 0), null);
assert.ok(Math.abs(inPersonMinusMail(sp, 0) - (60 / 150 - 240 / 350)) < 1e-12);
assert.equal(inPersonMinusMail(methodSplit([10, 4, 4, 0], [4, 4, 0]), 0), null);                     // no in-person votes at all: no difference to report
assert.deepEqual(methodSplit([10, 4, 5, 0], [4, 6, 0]).ip, [0, 0]);                                // mail above total cannot go negative
const mp = { A: { 1: [300, 1000], 2: [250] }, B: { 1: [90] } };
const v = vbmShareByPrecinct({ votes: { A: { city: "x", v: { 1: [1000, 400, 1, 1], 2: [1000, 450, 1, 1] } }, B: { city: "y", v: { 1: [600, 300, 1, 1] } }, C: { city: "y", v: { 1: [10, 5, 1, 1] } } } }, mp, [1, 2]);
assert.equal(v.rows.size, 2); assert.equal(v.rows.get("A").ballots, 450); assert.equal(v.rows.get("A").vbm, 250);   // the contest with the most ballots supplies both numbers
assert.equal(v.vbm, 340); assert.equal(v.ballots, 750); assert.ok(!v.rows.has("C"));                             // C has no vote-by-mail data: skipped
assert.deepEqual(vbmOf(v, (x) => x.city === "x"), { vbm: 250, ballots: 450, n: 1, rate: 250 / 450 }); assert.equal(vbmOf(v).rate, 340 / 750);
console.log("analysis tests pass");
