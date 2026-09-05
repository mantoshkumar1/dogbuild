/**
 * `update_control_comment` — the one write a headless worker needs while the
 * trusted identity transport is still blocked.
 *
 * Its authority comes from Worker CONFIGURATION, so the tests that matter are
 * the ones proving every target OTHER than a configured one is refused, and
 * refused before any upstream request.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { callTool, MAX_CONTROL_BODY_BYTES } from "../src/handlers.js";
import { parseControlComments } from "../src/control-comments.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, ctxFor, mockFetch } from "./helpers.mjs";

const SLOT = 5498666442;
const OTHER_SLOT = 5498666236;
const CONTROL_ENV = { ...ENV, CONTROL_COMMENTS: `mantoshkumar1/pingstep#${SLOT}` };
const BASE = "/repos/mantoshkumar1/pingstep";
const OK = { owner: "mantoshkumar1", repo: "pingstep", comment_id: SLOT };
const READ_CTX = { role: "read" };

function routes(updatedAt = "2026-09-05T13:00:00Z") {
  return {
    [`GET ${BASE}/issues/comments/${SLOT}`]: { body: { id: SLOT, updated_at: updatedAt } },
    [`PATCH ${BASE}/issues/comments/${SLOT}`]: { body: { id: SLOT, updated_at: "2026-09-05T14:00:00Z", html_url: "https://example.invalid/c", body: "ECHOED BODY" } },
  };
}

test("configuration parsing is fail-closed", () => {
  assert.throws(() => parseControlComments({}), (e) => e.class === ErrorClass.CONTROL_TARGET_DENIED);
  assert.throws(() => parseControlComments({ CONTROL_COMMENTS: "   " }), (e) => e.class === ErrorClass.CONTROL_TARGET_DENIED);
  for (const bad of ["not-a-target", "owner/repo", "owner/repo#", "owner#123", "owner/repo#abc", "a/b#1,broken"]) {
    assert.throws(() => parseControlComments({ CONTROL_COMMENTS: bad }), (e) => e.class === ErrorClass.CONTROL_TARGET_DENIED, bad);
  }
  assert.deepEqual(parseControlComments({ CONTROL_COMMENTS: "Owner/Repo#7, a/b#9" }), [
    { owner: "owner", repo: "repo", comment_id: 7 },
    { owner: "a", repo: "b", comment_id: 9 },
  ]);
});

test("with no configuration, every control write is refused and issues no request", async () => {
  const calls = mockFetch(routes());
  await assert.rejects(
    callTool(ENV, "update_control_comment", { ...OK, body: "x", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX),
    (e) => e.class === ErrorClass.CONTROL_TARGET_DENIED
  );
  assert.equal(calls.length, 0);
});

test("EVERY other target is rejected before any upstream request", async () => {
  const cases = [
    ["another comment in the same repo", { owner: "mantoshkumar1", repo: "pingstep", comment_id: OTHER_SLOT }],
    ["the same id in another allowlisted repo", { owner: "mantoshkumar1", repo: "dogbuild", comment_id: SLOT }],
    ["a nearby id", { owner: "mantoshkumar1", repo: "pingstep", comment_id: SLOT + 1 }],
    ["a different owner", { owner: "someone", repo: "pingstep", comment_id: SLOT }],
  ];
  for (const [label, target] of cases) {
    const calls = mockFetch(routes());
    await assert.rejects(
      callTool(CONTROL_ENV, "update_control_comment", { ...target, body: "x", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX),
      (e) => e.class === ErrorClass.CONTROL_TARGET_DENIED || e.class === ErrorClass.ALLOWLIST_DENIED,
      label
    );
    assert.equal(calls.length, 0, `${label}: no upstream request may be issued`);
  }
});

test("a non-integer comment id is refused", async () => {
  const calls = mockFetch(routes());
  for (const bad of ["5498666442", 1.5, null]) {
    await assert.rejects(
      callTool(CONTROL_ENV, "update_control_comment", { owner: "mantoshkumar1", repo: "pingstep", comment_id: bad, body: "x", expected_updated_at: "t" }, READ_CTX),
      (e) => e.class === ErrorClass.INVALID_INPUT || e.class === ErrorClass.CONTROL_TARGET_DENIED
    );
  }
  assert.equal(calls.length, 0);
});

test("optimistic concurrency is mandatory, not optional", async () => {
  const calls = mockFetch(routes());
  await assert.rejects(
    callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "x" }, READ_CTX),
    (e) => e.class === ErrorClass.INVALID_INPUT
  );
  assert.equal(calls.length, 0, "a blind overwrite must not even read the comment");
});

test("a stale expected_updated_at is refused before the PATCH", async () => {
  const calls = mockFetch(routes("2026-09-05T13:00:00Z"));
  await assert.rejects(
    callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "x", expected_updated_at: "2026-09-05T12:00:00Z" }, READ_CTX),
    (e) => e.class === ErrorClass.STALE_VERSION
  );
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 0);
});

test("the body is bounded more tightly than an ordinary comment", async () => {
  const calls = mockFetch(routes());
  await assert.rejects(
    callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "x".repeat(MAX_CONTROL_BODY_BYTES + 1), expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX),
    (e) => e.class === ErrorClass.INVALID_INPUT
  );
  await assert.rejects(
    callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX),
    (e) => e.class === ErrorClass.INVALID_INPUT
  );
  assert.equal(calls.length, 0);
});

test("a configured target with a fresh version succeeds and returns metadata only", async () => {
  const calls = mockFetch(routes("2026-09-05T13:00:00Z"));
  const r = await callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "IDLE_VALID", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX);
  assert.deepEqual(Object.keys(r).sort(), ["body_sha256", "body_bytes", "comment_id", "html_url", "repo", "updated_at"].sort());
  assert.equal(r.comment_id, SLOT);
  assert.equal(r.repo, "mantoshkumar1/pingstep");
  assert.match(r.body_sha256, /^[0-9a-f]{64}$/);
  assert.equal(r.body_bytes, 10);
  const serialized = JSON.stringify(r);
  assert.ok(!serialized.includes("IDLE_VALID"), "the request body must not be echoed back");
  assert.ok(!serialized.includes("ECHOED BODY"), "the upstream body must not be echoed back");
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 1);
});

test("repeated identical updates keep one comment id and never POST", async () => {
  const calls = mockFetch(routes("2026-09-05T13:00:00Z"));
  const a = await callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "same", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX);
  const b = await callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "same", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX);
  assert.equal(a.comment_id, b.comment_id);
  assert.equal(a.body_sha256, b.body_sha256);
  assert.equal(calls.filter((c) => c.method === "POST").length, 0);
});

test("an identity mismatch from upstream is a conflict", async () => {
  mockFetch({
    [`GET ${BASE}/issues/comments/${SLOT}`]: { body: { id: 999, updated_at: "2026-09-05T13:00:00Z" } },
  });
  await assert.rejects(
    callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "x", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX),
    (e) => e.class === ErrorClass.CONFLICT
  );
});

test("the repository allowlist still applies on top of the control list", async () => {
  const env = { ...CONTROL_ENV, ALLOWED_REPOS: "mantoshkumar1/dogbuild" };
  const calls = mockFetch(routes());
  await assert.rejects(
    callTool(env, "update_control_comment", { ...OK, body: "x", expected_updated_at: "2026-09-05T13:00:00Z" }, READ_CTX),
    (e) => e.class === ErrorClass.ALLOWLIST_DENIED
  );
  assert.equal(calls.length, 0);
});

test("the tool needs no role assertion and grants nothing else", async () => {
  const calls = mockFetch(routes("2026-09-05T13:00:00Z"));
  const r = await callTool(CONTROL_ENV, "update_control_comment", { ...OK, body: "ok", expected_updated_at: "2026-09-05T13:00:00Z" }, { role: "read" });
  assert.equal(r.comment_id, SLOT);
  // The same unsigned caller still cannot touch an ordinary comment.
  await assert.rejects(
    callTool(CONTROL_ENV, "update_issue_comment", { ...OK, body: "x" }, { role: "read" }),
    (e) => e.class === ErrorClass.ROLE_DENIED
  );
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 1);
});

test("a signed implementor context cannot widen the control target either", async () => {
  const ctx = await ctxFor("implementor", { comments: [OTHER_SLOT] }, {}, CONTROL_ENV);
  const calls = mockFetch(routes());
  await assert.rejects(
    callTool(CONTROL_ENV, "update_control_comment", { owner: "mantoshkumar1", repo: "pingstep", comment_id: OTHER_SLOT, body: "x", expected_updated_at: "t" }, ctx),
    (e) => e.class === ErrorClass.CONTROL_TARGET_DENIED,
    "an assertion scope must not override the configured control list"
  );
  assert.equal(calls.length, 0);
});
