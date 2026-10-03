// Conservative, calibrated head geometry. This never estimates intent, emotion,
// comprehension, identity or whether an answer was copied.
export const DEFAULT_POLICY = Object.freeze({ sustain_ms: 8000, cooldown_ms: 60000 });

export function poseFromLandmarks(points) {
  if (!points?.length) return null;
  const [nose, left, right, top, bottom] = [1, 234, 454, 10, 152].map(index => points[index]);
  if ([nose, left, right, top, bottom].some(point => !point || !Number.isFinite(point.x) || !Number.isFinite(point.y))) return null;
  const width = Math.abs(right.x - left.x), height = Math.abs(bottom.y - top.y);
  if (width < 0.04 || height < 0.06) return null; // Small/poorly framed faces are uncertain.
  return { yaw: (nose.x - (left.x + right.x) / 2) / width, pitch: (nose.y - top.y) / height };
}

export class CameraCuePolicy {
  constructor(policy = {}) {
    this.sustainMs = Math.max(8000, policy.sustain_ms || DEFAULT_POLICY.sustain_ms);
    this.cooldownMs = Math.max(60000, policy.cooldown_ms || DEFAULT_POLICY.cooldown_ms);
    this.neutral = null; this.calibration = []; this.lastSample = null;
    this.reason = null; this.since = null; this.lastCue = -Infinity; this.quietUntil = 0;
  }
  pause(now, milliseconds = 0) {
    this.reason = null; this.since = null; this.lastSample = null;
    this.quietUntil = Math.max(this.quietUntil, now + milliseconds);
  }
  recalibrate() { this.neutral = null; this.calibration = []; this.pause(0); }
  observe(pose, now) {
    if (!Number.isFinite(now)) return { state: "unavailable" };
    if (now < this.quietUntil) { this.reason = null; this.since = null; return { state: "paused" }; }
    if (this.lastSample != null && (now - this.lastSample > 2000 || now < this.lastSample)) { this.reason = null; this.since = null; }
    this.lastSample = now;
    if (pose && (!Number.isFinite(pose.yaw) || !Number.isFinite(pose.pitch))) { this.pause(now); return { state: "unavailable" }; }
    let calibrated = false;
    if (pose && !this.neutral) {
      this.reason = null; this.since = null; this.calibration.push(pose);
      if (this.calibration.length < 12) return { state: "calibrating" };
      const samples = this.calibration.slice(-12);
      const yaw = samples.map(p => p.yaw).sort((a, b) => a - b), pitch = samples.map(p => p.pitch).sort((a, b) => a - b);
      if (yaw[11] - yaw[0] > 0.08 || pitch[11] - pitch[0] > 0.08) { this.calibration.shift(); return { state: "calibrating" }; }
      this.neutral = { yaw: (yaw[5] + yaw[6]) / 2, pitch: (pitch[5] + pitch[6]) / 2 }; calibrated = true;
    }
    const reason = !pose ? "face_absent" : Math.abs(pose.yaw - this.neutral.yaw) > 0.22 || Math.abs(pose.pitch - this.neutral.pitch) > 0.22 ? "head_turned" : null;
    if (!reason) { this.reason = null; this.since = null; return { state: "face_visible", calibrated }; }
    if (reason !== this.reason) { this.reason = reason; this.since = now; }
    const duration = Math.round(now - this.since);
    if (duration >= this.sustainMs && now - this.lastCue >= this.cooldownMs) {
      this.lastCue = now;
      return { state: reason, cue: { reason, duration_ms: duration } };
    }
    return { state: reason };
  }
}

export function cueInstruction(reason) {
  return reason === "face_absent"
    ? "Your face has not been visible for several seconds. If you want camera cues, adjust the lighting or framing. You can stop the camera at any time."
    : reason === "head_turned"
      ? "Your head appears turned away for several seconds. When ready, return to the assessment and explain your reasoning in your own words."
      : "When ready, return to your answer and explain the reasoning in your own words.";
}
