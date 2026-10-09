const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const ts = require("typescript");
const source = fs.readFileSync("src/lib/playback-review.ts", "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const helpers = {};
vm.runInNewContext(compiled, { exports: helpers });
const { canConfirmPlayback, addPlayedInterval, recordPlaybackStep, playbackCoverage } = helpers;
const sample = (position, clockMs) => ({ position, clockMs, rate: 1 });
let intervals = recordPlaybackStep([], sample(0, 0), sample(5, 5000), 30);
assert.equal(playbackCoverage(intervals, 30), 5 / 30);
// Seeking to the ending never credits the unseen middle, even without a seeking event.
assert.equal(playbackCoverage(recordPlaybackStep(intervals, sample(5, 5000), sample(29, 5100), 30), 30), 5 / 30);
intervals = recordPlaybackStep(intervals, null, sample(25, 6000), 30);
intervals = recordPlaybackStep(intervals, sample(25, 6000), sample(30, 11000), 30);
assert.equal(playbackCoverage(intervals, 30), 10 / 30);
assert.ok(playbackCoverage(intervals, 30) < 0.95);
// Rewatching overlaps never increases credit beyond the covered timeline.
intervals = addPlayedInterval([], 0, 10, 30);
intervals = addPlayedInterval(intervals, 5, 15, 30);
assert.equal(playbackCoverage(intervals, 30), 0.5);
intervals = addPlayedInterval(intervals, 18, 30, 30);
assert.equal(playbackCoverage(intervals, 30), 0.9);
intervals = addPlayedInterval(intervals, 15, 18, 30);
assert.equal(playbackCoverage(intervals, 30), 1);
// Small leading/trailing rounding gaps fit the explicit 95 percent threshold.
assert.ok(playbackCoverage(addPlayedInterval([], 0.2, 29.8, 30), 30) >= 0.95);
assert.equal(playbackCoverage([], Number.NaN), 0);
assert.equal(playbackCoverage([], 0), 0);
assert.equal(canConfirmPlayback(1, false), false);
assert.equal(canConfirmPlayback(0.5, true), false);
assert.equal(canConfirmPlayback(0.95, true), true);
assert.equal(canConfirmPlayback(Number.NaN, true), false);
console.log("Playback review coverage: 14 checks passed.");
