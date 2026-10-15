import test from "node:test";
import assert from "node:assert/strict";
import { SubmissionRecovery, answerLocked, restoreAssessment } from "./submissionRecovery.js";

const firstId = "d130ef0a-9d1c-4e93-a43d-d535045d1627", secondId = "69a89b21-b402-47fb-abef-a84ea064961a";
function fixture() {
  const values = new Map(); let calls = 0;
  const storage = () => ({ getItem: key => values.get(key), setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) });
  return { storage, values, recovery: new SubmissionRecovery({ storage, uuid: () => [firstId, secondId][calls++] }) };
}

test("a lost submission response reuses its request ID, including after refresh", () => {
  const f = fixture(), payload = { code: "", answer: "First line\nSecond line" };
  assert.equal(f.recovery.request(7, payload), firstId);
  assert.equal(f.recovery.request(7, payload), firstId);
  const refreshed = new SubmissionRecovery({ storage: f.storage, uuid: () => { throw new Error("A retry must not allocate an ID"); } });
  assert.equal(refreshed.request(7, payload), firstId);
});

test("a confirmed response permits a deliberate practice retest, and late receipts cannot clear newer work", () => {
  const f = fixture(), payload = { code: "print(5)", answer: "" };
  f.recovery.request(7, payload); f.recovery.settle(7, firstId);
  assert.equal(f.recovery.request(7, payload), secondId);
  f.recovery.settle(7, firstId);
  assert.equal(f.recovery.request(7, payload), secondId);
});

test("saved assessment answers and feedback win over stale drafts, while unanswered drafts survive", () => {
  const f = fixture();
  f.recovery.saveDraft(1, { code: "", answer: "stale draft" });
  f.recovery.saveDraft(2, { code: "", answer: "Work in progress\nSecond line" });
  const attempt = { question_id: 1, answer: "0", status: "completed", feedback: { explanation: "Saved feedback" } };
  const restored = restoreAssessment({ questions: [{ id: 1 }, { id: 2 }, { id: 3 }], attempts: [attempt] }, f.recovery);
  assert.deepEqual(restored.answers, { 1: "0", 2: "Work in progress\nSecond line", 3: "" });
  assert.equal(restored.results[1], attempt);
  assert.equal(answerLocked(attempt, "in_progress"), true);
  assert.equal(answerLocked({ status: "failed" }, "in_progress"), false);
  assert.equal(answerLocked(null, "completed"), true);
  const retried = restoreAssessment({ questions: [{ id: 2 }], attempts: [{ question_id: 2, status: "failed", answer: "invalid old answer" }] }, f.recovery);
  assert.equal(retried.answers[2], "Work in progress\nSecond line");
});

test("blocked or malformed browser storage cannot interrupt answer editing or retry identity", () => {
  const recovery = new SubmissionRecovery({ storage: () => { throw new Error("Storage denied"); }, uuid: () => firstId });
  const payload = { code: "", answer: "Accessible answer" };
  recovery.saveDraft(1, payload);
  assert.deepEqual(recovery.draft(1), payload);
  assert.equal(recovery.request(1, payload), recovery.request(1, payload));
  const f = fixture(); f.values.set("labtwin_answer_2", "bad json"); f.values.set("labtwin_submission_2", "{}");
  assert.equal(f.recovery.draft(2), null);
  assert.equal(f.recovery.request(2, payload), firstId);
});
