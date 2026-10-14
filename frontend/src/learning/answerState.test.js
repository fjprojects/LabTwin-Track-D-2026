import assert from "node:assert/strict";
import test from "node:test";
import { answerState, canCheckUnderstanding } from "./answerState.js";

test("only a signed-in student sees checks on a saved grounded exchange", () => {
  const exchange = Object.freeze({ id: 8, grounded: true, mode: "ai_grounded" });
  assert.equal(canCheckUnderstanding("student", exchange), true);
  for (const role of ["teacher", "admin", "", null, undefined]) assert.equal(canCheckUnderstanding(role, exchange), false);
  assert.equal(canCheckUnderstanding("student", { ...exchange, grounded: false }), false);
  assert.equal(canCheckUnderstanding("student", { grounded: true }), false);
  assert.equal(canCheckUnderstanding("student", { ...exchange, grounded: "true" }), false);
});

test("an extractive fallback is explicitly labeled as source excerpts", () => {
  assert.deepEqual(answerState({ mode: "source_excerpts", grounded: true }), { kind: "excerpts", label: "Source excerpts" });
});

test("only the explicit grounded AI mode earns an AI explanation label", () => {
  assert.equal(answerState({ mode: "ai_grounded", grounded: true }).kind, "ai");
  for (const item of [{ grounded: true }, { mode: "unexpected", grounded: true }, { mode: "ai_grounded" }]) {
    assert.equal(answerState(item).kind, "saved");
  }
});

test("insufficient or ungrounded material stays an unsupported state", () => {
  for (const item of [{ mode: "insufficient_sources", grounded: false }, { mode: "source_excerpts", grounded: false }, { mode: "ai_grounded", grounded: false }]) {
    assert.deepEqual(answerState(item), { kind: "unsupported", label: "More material needed" });
  }
});

test("presentation does not rewrite answer text, citation IDs, locations or links", () => {
  const citation = Object.freeze({ id: 19, page_number: 6, label: "Java OOP — Page 6", href: "#source=19" });
  const item = Object.freeze({ id: 8, answer: "Original course text", grounded: true, mode: "source_excerpts", citations: Object.freeze([citation]) });
  answerState(item); canCheckUnderstanding("teacher", item);
  assert.equal(item.answer, "Original course text");
  assert.deepEqual(item.citations[0], citation);
});
