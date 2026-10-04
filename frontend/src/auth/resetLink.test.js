import test from "node:test";
import assert from "node:assert/strict";
import { initialResetTarget, parseResetFragment, RESET_STORAGE_KEY } from "./resetLink.js";

const fragment = "#password-reset=MQ:abcdef-0123456789abcdef0123456789abcdef";

test("email fragment opens the reset flow with separate uid and token", () => {
  assert.deepEqual(parseResetFragment(fragment), { uid: "MQ", token: "abcdef-0123456789abcdef0123456789abcdef" });
});

test("other application fragments and malformed reset credentials are ignored", () => {
  for (const value of [null, "#source=23", "?password-reset=MQ:token", fragment + "&next=https://attacker.test", fragment + "<script>", "#password-reset=:token", "#password-reset=" + "x".repeat(200)]) {
    assert.equal(parseResetFragment(value), null);
  }
});

test("a validated private-gate tab handoff restores the reset flow", () => {
  const previousWindow = globalThis.window, previousStorage = globalThis.sessionStorage;
  try {
    globalThis.window = { location: { hash: "" } };
    globalThis.sessionStorage = { getItem: key => key === RESET_STORAGE_KEY ? fragment : null };
    assert.deepEqual(initialResetTarget(), parseResetFragment(fragment));
    globalThis.window.location.hash = fragment.replace("MQ:", "Mg:");
    assert.equal(initialResetTarget().uid, "Mg");
  } finally { globalThis.window = previousWindow; globalThis.sessionStorage = previousStorage; }
});

test("blocked tab storage does not crash normal login", () => {
  const previousWindow = globalThis.window, previousStorage = globalThis.sessionStorage;
  try {
    globalThis.window = { location: { hash: "" } };
    globalThis.sessionStorage = { getItem: () => { throw new Error("Storage disabled"); } };
    assert.equal(initialResetTarget(), null);
  } finally { globalThis.window = previousWindow; globalThis.sessionStorage = previousStorage; }
});
