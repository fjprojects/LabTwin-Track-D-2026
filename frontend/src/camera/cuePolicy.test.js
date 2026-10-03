import test from "node:test";
import assert from "node:assert/strict";
import { CameraCuePolicy, poseFromLandmarks, cueInstruction } from "./cuePolicy.js";

function calibrated() {
  const detector = new CameraCuePolicy();
  for (let t = 0; t < 3000; t += 250) detector.observe({ yaw: 0, pitch: 0.5 }, t);
  return detector;
}
function sequence(detector, pose, from, until) {
  const observations = [];
  for (let t = from; t <= until; t += 250) observations.push(detector.observe(pose, t));
  return observations.filter(o => o.cue);
}

test("requires stable calibration and ignores normal small head movement", () => {
  const detector = calibrated();
  assert.ok(detector.neutral);
  assert.equal(sequence(detector, { yaw: .12, pitch: .55 }, 3000, 18000).length, 0);
});
test("brief head turns, blinks and brief face absence do not produce a cue", () => {
  const detector = calibrated();
  assert.equal(sequence(detector, { yaw: .4, pitch: .5 }, 3000, 10500).length, 0);
  detector.observe({ yaw: 0, pitch: .5 }, 10750);
  assert.equal(sequence(detector, null, 11000, 15000).length, 0);
  detector.observe({ yaw: 0, pitch: .5 }, 15250);
  assert.equal(sequence(detector, null, 15500, 18000).length, 0);
});
test("a sustained turn produces a neutral cue after eight seconds", () => {
  const cues = sequence(calibrated(), { yaw: .4, pitch: .5 }, 3000, 11000);
  assert.deepEqual(cues.map(o => o.cue), [{ reason: "head_turned", duration_ms: 8000 }]);
  assert.ok(!/cheat|copied|understands/i.test(cueInstruction("head_turned")));
});
test("sustained face absence is a framing cue even before calibration", () => {
  assert.equal(sequence(new CameraCuePolicy(), null, 0, 8000)[0].cue.reason, "face_absent");
});
test("does not accumulate disconnected face-absence intervals", () => {
  const detector = calibrated();
  assert.equal(sequence(detector, null, 3000, 8000).length, 0);
  assert.equal(sequence(detector, null, 15000, 20000).length, 0);
});
test("rate limits reminders across ongoing observations", () => {
  const detector = calibrated();
  const cues = sequence(detector, null, 3000, 75000);
  assert.equal(cues.length, 2);
  assert.ok(cues[1].cue.duration_ms - cues[0].cue.duration_ms >= 60000);
});
test("pauses for reading sources and optional eyes-closed explanations", () => {
  const detector = calibrated();
  sequence(detector, null, 3000, 9000);
  detector.pause(9250, 15000);
  assert.equal(sequence(detector, null, 9500, 27000).length, 0);
  assert.equal(sequence(detector, null, 27250, 32250).length, 1);
});
test("calibration follows the learner's neutral posture", () => {
  const detector = new CameraCuePolicy();
  sequence(detector, { yaw: .2, pitch: .65 }, 0, 3000);
  assert.equal(sequence(detector, { yaw: .32, pitch: .7 }, 3250, 22000).length, 0);
});
test("rejects malformed geometry and tiny, poorly framed faces", () => {
  assert.equal(poseFromLandmarks([]), null);
  const points = Array.from({ length: 478 }, () => ({ x: .5, y: .5 }));
  assert.equal(poseFromLandmarks(points), null);
  const detector = calibrated();
  assert.equal(detector.observe({ yaw: NaN, pitch: .5 }, 3500).state, "unavailable");
});
test("recalibration discards old camera posture and interrupted observations", () => {
  const detector = calibrated(); sequence(detector, null, 3000, 9000); detector.recalibrate();
  assert.equal(detector.neutral, null);
  assert.equal(sequence(detector, { yaw: -.2, pitch: .5 }, 9250, 12250).length, 0);
  assert.equal(sequence(detector, { yaw: -.2, pitch: .5 }, 12500, 20500).length, 0);
});
