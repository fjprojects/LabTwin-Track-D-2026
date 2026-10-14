import assert from "node:assert/strict";
import test from "node:test";
import { topicPayload, duplicateTopicMessage } from "./topicForm.js";

const topics = Object.freeze([Object.freeze({ id: 7, name: "Polymorphism" }), Object.freeze({ id: 11, name: "Inheritance" })]);

test("a new topic is trimmed and sends an empty prerequisite list by default", () => {
  assert.deepEqual(topicPayload("  Method overloading  ", "", topics), { name: "Method overloading", prerequisites: [] });
});

test("a course-owned prerequisite is sent as an integer ID", () => {
  assert.deepEqual(topicPayload("Overriding", "7", topics), { name: "Overriding", prerequisites: [7] });
});

test("existing topics, including automatically extracted topics, are not resubmitted", () => {
  assert.throws(() => topicPayload(" Polymorphism ", "", topics), /already exists in this course/);
});

test("blank, non-text and oversized topic names are rejected before a POST", () => {
  for (const name of [undefined, null, false, 42, [], {}, "", "   ", "x".repeat(201)]) {
    assert.throws(() => topicPayload(name, "", topics), /Enter a topic name of up to 200 characters/);
  }
});

test("invalid, missing and foreign prerequisite IDs cannot be submitted", () => {
  for (const id of ["999", "abc", "0", "-1", "1.5", null, undefined, "9007199254740992"]) {
    assert.throws(() => topicPayload("Overriding", id, topics), /Choose prerequisites from this course/);
  }
});

test("a topic absent from the selected course remains a valid new name", () => {
  assert.deepEqual(topicPayload("Polymorphism", "", []), { name: "Polymorphism", prerequisites: [] });
});

test("the maximum name length is allowed and validation retains course topic data", () => {
  assert.equal(topicPayload("x".repeat(200), "11", topics).name.length, 200);
  assert.deepEqual(topics, [{ id: 7, name: "Polymorphism" }, { id: 11, name: "Inheritance" }]);
});

test("duplicate warnings appear while typing without mutating course topics", () => {
  assert.match(duplicateTopicMessage("  Polymorphism ", topics), /already exists/);
  for (const value of ["", " ", undefined, "Overriding"]) assert.equal(duplicateTopicMessage(value, topics), "");
  // Match the backend's exact-name duplicate rule, including letter case.
  assert.equal(duplicateTopicMessage("polymorphism", topics), "");
  assert.equal(topics[0].name, "Polymorphism");
});
