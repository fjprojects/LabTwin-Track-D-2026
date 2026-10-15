import test from "node:test";
import assert from "node:assert/strict";
import { ActivityQueue, visibilityTransition } from "./activityQueue.js";

const observed = "2026-10-14T20:00:00Z";
function fixture(send, saved) {
  let visible, stored;
  const tracker = new ActivityQueue({ send, saved, changed: value => { visible = value; }, persist: value => { stored = value; } });
  return { tracker, visible: () => visible, stored: () => JSON.parse(stored || "[]") };
}

test("a hidden departure counts once; focus loss is not a second departure", () => {
  let state = visibilityTransition(false, true);
  assert.equal(state.departed, true);
  assert.equal(visibilityTransition(state.hidden, true).departed, false);
  state = visibilityTransition(state.hidden, false);
  assert.equal(state.departed, false);
  assert.equal(visibilityTransition(state.hidden, true).departed, true);
});

test("a departure during initial history loading waits for reconciliation", async () => {
  let calls = 0;
  const f = fixture(async events => { calls++; return { events, tab_switches: 4 }; });
  f.tracker.record("tab_hidden", {}, "new", observed);
  assert.equal(calls, 0);
  assert.equal(f.visible().tabSwitches, 1);
  f.tracker.initialize({ tab_switches: 3 });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1);
  assert.equal(f.visible().tabSwitches, 4);
  assert.deepEqual(f.stored(), []);
});

test("a lost response retries the same event ID, without multiplying the count", async () => {
  const ids = [], savedIds = new Set();
  let fail = true;
  const f = fixture(async events => {
    ids.push(events[0].event_id); events.forEach(row => savedIds.add(row.event_id));
    if (fail) throw new Error("response lost");
    return { events, tab_switches: savedIds.size };
  });
  f.tracker.initialize({}); f.tracker.record("tab_hidden", {}, "once", observed);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(f.visible().syncError, /waiting to sync/);
  assert.equal(f.visible().tabSwitches, 1);
  fail = false; await f.tracker.flush();
  assert.deepEqual(ids, ["once", "once"]);
  assert.equal(f.visible().tabSwitches, 1);
  assert.equal(f.visible().syncError, "");
});

test("refresh reconciles accepted queue entries and preserves separate focus/paste counts", async () => {
  const saved = JSON.stringify([{ event_id: "saved", kind: "tab_hidden", detail: { observed_at: observed } }, { event_id: "focus", kind: "window_blur", detail: { observed_at: observed } }]);
  const f = fixture(async events => ({ events, tab_switches: 1, focus_losses: 1 }), saved);
  f.tracker.initialize({ events: [{ event_id: "saved" }], tab_switches: 1 });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(f.visible().tabSwitches, 1);
  assert.equal(f.visible().focusLosses, 1);
  assert.equal(f.visible().blockedPastes, 0);
});

test("only allowlisted metadata is retained; malformed storage never breaks editing", () => {
  const f = fixture(async () => {}, "bad JSON");
  f.tracker.record("paste_allowed", { characters: 4, clipboard: "private", url: "private", cheating: true }, "paste", observed);
  assert.deepEqual(f.stored()[0].detail, { observed_at: observed, characters: 4 });
  assert.equal(f.visible().allowedPastes, 1);
  assert.equal(f.visible().blockedPastes, 0);
  f.tracker.record("cheating", {}, "invalid", observed);
  assert.equal(f.stored().length, 1);
});

test("no-receipt responses fail safely instead of looping forever", async () => {
  let calls = 0;
  const f = fixture(async () => { calls++; return { events: [] }; });
  f.tracker.initialize({}); f.tracker.record("tab_hidden", {}, "pending", observed);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1);
  assert.match(f.visible().syncError, /waiting to sync/);
  f.tracker.dispose(); await f.tracker.flush();
  assert.equal(calls, 1);
});
