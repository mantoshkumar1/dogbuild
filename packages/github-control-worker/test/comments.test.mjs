import { test } from "node:test";
import assert from "node:assert/strict";
import { callTool, MAX_COMMENT_BODY_BYTES } from "../src/handlers.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, ctxFor, mockFetch } from "./helpers.mjs";

const BASE = "/repos/mantoshkumar1/pingstep";
const ARGS = { owner: "mantoshkumar1", repo: "pingstep", comment_id: 5498666442 };
const CTX = await ctxFor("reviewer", { comments: [5498666442] });

test("a stale expected_updated_at is refused BEFORE any write", async () => {
  const calls = mockFetch({
    [`GET ${BASE}/issues/comments/5498666442`]: { body: { id: 5498666442, updated_at: "2026-09-05T13:00:00Z" } },
  });
  await assert.rejects(
    callTool(ENV, "update_issue_comment", { ...ARGS, body: "new", expected_updated_at: "2026-09-05T12:00:00Z" }, CTX),
    (e) => e.class === ErrorClass.STALE_VERSION
  );
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 0, "no PATCH may be issued when the version is stale");
});

test("a matching expected_updated_at proceeds and returns a body digest", async () => {
  const calls = mockFetch({
    [`GET ${BASE}/issues/comments/5498666442`]: { body: { id: 5498666442, updated_at: "2026-09-05T13:00:00Z" } },
    [`PATCH ${BASE}/issues/comments/5498666442`]: { body: { id: 5498666442, updated_at: "2026-09-05T14:00:00Z", html_url: "https://example.invalid/c" } },
  });
  const r = await callTool(ENV, "update_issue_comment", { ...ARGS, body: "new body", expected_updated_at: "2026-09-05T13:00:00Z" }, CTX);
  assert.equal(r.comment_id, 5498666442);
  assert.equal(r.repo, "mantoshkumar1/pingstep");
  assert.match(r.body_sha256, /^[0-9a-f]{64}$/);
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 1);
});

test("the comment id is stable: repeated updates never create a second comment", async () => {
  const calls = mockFetch({
    [`PATCH ${BASE}/issues/comments/5498666442`]: { body: { id: 5498666442, updated_at: "2026-09-05T14:00:00Z" } },
  });
  const a = await callTool(ENV, "update_issue_comment", { ...ARGS, body: "same" }, CTX);
  const b = await callTool(ENV, "update_issue_comment", { ...ARGS, body: "same" }, CTX);
  assert.equal(a.comment_id, b.comment_id);
  assert.equal(a.body_sha256, b.body_sha256, "identical bodies produce an identical digest");
  assert.equal(calls.filter((c) => c.method === "POST").length, 0, "an update must never POST a new comment");
});

test("an identity mismatch in the response is a conflict", async () => {
  mockFetch({ [`PATCH ${BASE}/issues/comments/5498666442`]: { body: { id: 999, updated_at: "x" } } });
  await assert.rejects(
    callTool(ENV, "update_issue_comment", { ...ARGS, body: "x" }, CTX),
    (e) => e.class === ErrorClass.CONFLICT
  );
});

test("comment bodies are bounded", async () => {
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "update_issue_comment", { ...ARGS, body: "x".repeat(MAX_COMMENT_BODY_BYTES + 1) }, CTX),
    (e) => e.class === ErrorClass.INVALID_INPUT
  );
  await assert.rejects(callTool(ENV, "update_issue_comment", { ...ARGS, body: "" }, CTX), (e) => e.class === ErrorClass.INVALID_INPUT);
  assert.equal(calls.length, 0);
});

test("upstream statuses map onto distinct deterministic error classes", async () => {
  const cases = [
    [401, {}, ErrorClass.UNAUTHORIZED],
    [403, {}, ErrorClass.FORBIDDEN],
    [403, { "x-ratelimit-remaining": "0" }, ErrorClass.RATE_LIMIT],
    [404, {}, ErrorClass.NOT_FOUND],
    [409, {}, ErrorClass.CONFLICT],
    [422, {}, ErrorClass.UNPROCESSABLE],
    [429, {}, ErrorClass.RATE_LIMIT],
    [500, {}, ErrorClass.UPSTREAM_ERROR],
  ];
  for (const [status, headers, expected] of cases) {
    mockFetch({ [`PATCH ${BASE}/issues/comments/5498666442`]: { status, headers } });
    await assert.rejects(
      callTool(ENV, "update_issue_comment", { ...ARGS, body: "x" }, CTX),
      (e) => e.class === expected,
      `status ${status} should map to ${expected}`
    );
  }
});

test("a malformed upstream body is its own error class", async () => {
  mockFetch({ [`PATCH ${BASE}/issues/comments/5498666442`]: { text: "<html>not json</html>" } });
  await assert.rejects(
    callTool(ENV, "update_issue_comment", { ...ARGS, body: "x" }, CTX),
    (e) => e.class === ErrorClass.UPSTREAM_MALFORMED
  );
});

test("a timeout is its own error class and leaks nothing", async () => {
  globalThis.fetch = async () => {
    const err = new Error("aborted");
    err.name = "AbortError";
    throw err;
  };
  await assert.rejects(callTool(ENV, "update_issue_comment", { ...ARGS, body: "x" }, CTX), (e) => {
    assert.equal(e.class, ErrorClass.TIMEOUT);
    assert.ok(!e.message.includes(ENV.GITHUB_TOKEN));
    return true;
  });
});

test("no error message ever contains the token or the body", async () => {
  mockFetch({ [`PATCH ${BASE}/issues/comments/5498666442`]: { status: 403 } });
  const secretBody = "SENSITIVE-DRAFT-TEXT";
  await assert.rejects(callTool(ENV, "update_issue_comment", { ...ARGS, body: secretBody }, CTX), (e) => {
    const serialized = JSON.stringify(e.toJSON());
    assert.ok(!serialized.includes(ENV.GITHUB_TOKEN));
    assert.ok(!serialized.includes(secretBody));
    return true;
  });
});
