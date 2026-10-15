import test from "node:test";
import assert from "node:assert/strict";
import { CameraSetupError, cameraErrorText, within } from "./setup.js";

test("permission/device failures have useful, safe messages and an assessment alternative", () => {
  for (const name of ["NotAllowedError", "NotFoundError", "NotReadableError", "SecurityError", "AbortError"]) {
    const message = cameraErrorText({ name, message: "private device /internal/location" });
    assert.doesNotMatch(message, /private|internal/);
    assert.match(message, /continue|answers remain/);
  }
  assert.match(cameraErrorText({ name: "Unknown", message: "token=secret" }), /temporarily unavailable/);
  assert.doesNotMatch(cameraErrorText({ message: "token=secret" }), /secret/);
});

test("unanswered browser permission terminates, and a later stream is stopped", async () => {
  let permission, stopped = 0;
  const stream = { getTracks: () => [{ stop: () => { stopped++; } }] };
  const pending = new Promise(resolve => { permission = resolve; });
  await assert.rejects(within(pending, 10, "Permission timed out", value => value.getTracks().forEach(track => track.stop())), CameraSetupError);
  permission(stream);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(stopped, 1);
});

test("successful setup does not dispose a live stream; provider failure remains catchable", async () => {
  let disposed = false;
  const result = await within(Promise.resolve("ready"), 20, "Timeout", () => { disposed = true; });
  assert.equal(result, "ready"); assert.equal(disposed, false);
  await assert.rejects(within(Promise.reject(new Error("offline")), 20, "Timeout"), /offline/);
});
