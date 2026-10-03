import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createServer } from "vite";

// Load the real Vite modules in SSR mode; no browser or UI pass is claimed.
const vite = await createServer({ server: { middlewareMode: true, hmr: false }, appType: "custom" });
after(() => vite.close());
const { default: client } = await vite.ssrLoadModule("/src/api.js");
const { errorText } = await vite.ssrLoadModule("/src/learning/api.js");

test("real API client has a finite response deadline", () => {
  assert.ok(client.defaults.timeout > 0, "Axios defaults to an unlimited wait without a timeout.");
  assert.ok(client.defaults.timeout <= 180000);
});

test("malformed server errors cannot become React-rendered objects", () => {
  const message = errorText({ response: { data: { error: { private: "unexpected provider object" } } } });
  assert.equal(typeof message, "string");
  assert.ok(!message.includes("unexpected provider object"));
});

test("timeout explains refresh before safely repeating a mutation", () => {
  const message = errorText({ code: "ECONNABORTED" });
  assert.match(message, /timed out/i);
  assert.match(message, /refresh/i);
});

test("known safe course errors retain actionable feedback", () => {
  assert.equal(errorText({ response: { data: { error: "No verified unique questions are available." } } }), "No verified unique questions are available.");
});
