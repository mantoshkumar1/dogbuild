/**
 * Regression suite for FINDING 2 of
 * DB-164-CODEX-GITHUB-CONTROL-TOOLS-IMPLEMENTATION-REVIEW-01.
 *
 * A verified signature is not authorization. Every write must be bound to a
 * target the assertion actually names, and every denial must happen before a
 * single upstream request is issued.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { callTool } from "../src/handlers.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, SHA, ctxFor, mockFetch } from "./helpers.mjs";

const REPO = { owner: "mantoshkumar1", repo: "pingstep" };

test("an assertion bound to one issue cannot write to another", async () => {
  const ctx = await ctxFor("implementor", { issues: [164] });
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "update_issue", { ...REPO, issue_number: 999, body: "unrelated" }, ctx),
    (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE
  );
  assert.equal(calls.length, 0, "a scope denial must issue no upstream request");
});

test("an assertion declaring no issue scope authorizes no issue write at all", async () => {
  const ctx = await ctxFor("implementor", {});
  const calls = mockFetch();
  for (const [tool, args] of [
    ["update_issue", { issue_number: 1, body: "x" }],
    ["add_issue_comment", { issue_number: 1, body: "x" }],
    ["add_labels", { issue_number: 1, labels: ["x"] }],
    ["remove_label", { issue_number: 1, name: "x" }],
    ["add_assignees", { issue_number: 1, assignees: ["x"] }],
    ["remove_assignees", { issue_number: 1, assignees: ["x"] }],
  ]) {
    await assert.rejects(
      callTool(ENV, tool, { ...REPO, ...args }, ctx),
      (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE,
      `${tool} must be refused`
    );
  }
  assert.equal(calls.length, 0);
});

test("a write to an in-scope issue proceeds", async () => {
  const ctx = await ctxFor("implementor", { issues: [164] });
  const calls = mockFetch({ "PATCH /repos/mantoshkumar1/pingstep/issues/164": { body: { number: 164, state: "open" } } });
  const r = await callTool(ENV, "update_issue", { ...REPO, issue_number: 164, body: "scoped" }, ctx);
  assert.equal(r.number, 164);
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 1);
});

test("comment updates are bound to the asserted comment id", async () => {
  const ctx = await ctxFor("reviewer", { comments: [111] });
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "update_issue_comment", { ...REPO, comment_id: 222, body: "x" }, ctx),
    (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE
  );
  assert.equal(calls.length, 0);
});

test("review publication is bound to the asserted PR", async () => {
  const ctx = await ctxFor("reviewer", { pull_requests: [165] });
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "publish_review", { ...REPO, pull_number: 999, expected_head_sha: SHA, body: "x" }, ctx),
    (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE
  );
  assert.equal(calls.length, 0, "the head re-read must not even happen for an out-of-scope PR");
});

test("a PR may only be opened from the asserted branch", async () => {
  const ctx = await ctxFor("implementor", { branch: "db-164-authorized" });
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "create_pull_request", { ...REPO, title: "t", head: "another-branch", base: "main" }, ctx),
    (e) => e.class === ErrorClass.BRANCH_DENIED
  );
  assert.equal(calls.length, 0);

  mockFetch({ "POST /repos/mantoshkumar1/pingstep/pulls": { body: { number: 5, head: { sha: SHA } } } });
  const ok = await callTool(ENV, "create_pull_request", { ...REPO, title: "t", head: "db-164-authorized", base: "main" }, ctx);
  assert.equal(ok.number, 5);
});

test("branch and file writes require an asserted branch", async () => {
  const ctx = await ctxFor("implementor", {});
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "create_branch", { ...REPO, new_branch: "anything" }, ctx),
    (e) => e.class === ErrorClass.BRANCH_DENIED
  );
  await assert.rejects(
    callTool(ENV, "create_or_update_file", { ...REPO, path: "p", content: "c", message: "m", branch: "anything" }, ctx),
    (e) => e.class === ErrorClass.BRANCH_DENIED
  );
  assert.equal(calls.length, 0);
});

test("issue creation requires explicit authorization in the assertion", async () => {
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "create_issue", { ...REPO, title: "t" }, await ctxFor("implementor", {})),
    (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE
  );
  assert.equal(calls.length, 0);
  mockFetch({ "POST /repos/mantoshkumar1/pingstep/issues": { body: { number: 7 } } });
  const ok = await callTool(ENV, "create_issue", { ...REPO, title: "t" }, await ctxFor("implementor", { allow_create_issue: true }));
  assert.equal(ok.number, 7);
});

test("project writes are bound to the asserted project", async () => {
  const ctx = await ctxFor("implementor", { projects: [3] });
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "add_project_item", { login: "mantoshkumar1", project_number: 9, content_node_id: "N" }, ctx),
    (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE
  );
  await assert.rejects(
    callTool(ENV, "update_project_item_field", { login: "mantoshkumar1", project_number: 9, item_id: "I", field_id: "F", text: "v" }, ctx),
    (e) => e.class === ErrorClass.TARGET_NOT_IN_SCOPE
  );
  assert.equal(calls.length, 0);
});

test("reads are unaffected by write scoping", async () => {
  const ctx = await ctxFor("implementor", {});
  mockFetch({ "GET /repos/mantoshkumar1/pingstep/issues/999": { body: { number: 999, title: "t", labels: [] } } });
  const r = await callTool(ENV, "get_issue", { ...REPO, issue_number: 999 }, ctx);
  assert.equal(r.number, 999, "an out-of-scope issue is still readable; scoping governs writes");
});
