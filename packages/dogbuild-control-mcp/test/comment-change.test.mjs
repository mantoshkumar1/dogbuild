import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  CommentChangeOperation,
  MAX_CHANGE_TEXT_BYTES,
  MAX_EVIDENCE_REFS,
  MAX_EVIDENCE_REF_BYTES,
} from "../src/comment-change.js";
import { ErrorClass } from "../src/errors.js";
import { callTool } from "../src/handlers.js";
import { ENV, mockFetch, rpc } from "./helpers.mjs";

const BASE = Object.freeze({
  owner: "mantoshkumar1",
  repo: "dogbuild",
  issue_number: 164,
  original_comment_id: 5578546622,
});

const APPEND = Object.freeze({
  ...BASE,
  prior_statement: "The fourth server would expose a comment-writing tool.",
  new_statement: "The fourth server returns a safe append-only command instead.",
  evidence_refs: ["https://github.com/mantoshkumar1/dogbuild/issues/164#issuecomment-5579218361"],
  effect: "Do not rely on an edit or delete capability.",
});

function expectedUrl() {
  return "https://github.com/mantoshkumar1/dogbuild/issues/164#issuecomment-5578546622";
}

async function call(args) {
  return callTool(ENV, "handle_comment_change_request", args);
}

test("CORRECTION returns the canonical append-only envelope and no upstream request", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const result = await call({ ...APPEND, operation: CommentChangeOperation.CORRECTION });

  assert.equal(result.decision, "APPEND_COMMENT");
  assert.equal(result.operation, "CORRECTION");
  assert.equal(result.original_comment_url, expectedUrl());
  assert.equal(result.authorship_verified, false);
  assert.equal(result.original_comment_verified, false);
  assert.equal(result.authoritative, false);
  assert.equal(result.github_command.capability, "add_issue_comment");
  assert.equal(result.github_command.preferred_tool, "dogbuild-github-core_add_issue_comment");
  assert.deepEqual(
    {
      owner: result.github_command.arguments.owner,
      repo: result.github_command.arguments.repo,
      issue_number: result.github_command.arguments.issue_number,
    },
    { owner: "mantoshkumar1", repo: "dogbuild", issue_number: 164 }
  );
  assert.equal(
    result.github_command.arguments.body,
    `CORRECTION / SUPERSEDES ${expectedUrl()}\n\n` +
      "Incorrect prior statement:\nThe fourth server would expose a comment-writing tool.\n\n" +
      "Correct statement:\nThe fourth server returns a safe append-only command instead.\n\n" +
      "Evidence:\n- https://github.com/mantoshkumar1/dogbuild/issues/164#issuecomment-5579218361\n\n" +
      "Effect:\nDo not rely on an edit or delete capability."
  );
  assert.equal(calls.length, 0);
});

test("STATUS_UPDATE and DISPUTE use distinct deterministic envelopes", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const status = await call({ ...APPEND, operation: CommentChangeOperation.STATUS_UPDATE });
  const dispute = await call({ ...APPEND, operation: CommentChangeOperation.DISPUTE });

  assert.match(status.github_command.arguments.body, /^STATUS UPDATE \/ REFERENCES /);
  assert.match(status.github_command.arguments.body, /Previous state:/);
  assert.match(status.github_command.arguments.body, /Current state:/);
  assert.match(dispute.github_command.arguments.body, /^DISPUTE \/ CONTRADICTS /);
  assert.match(dispute.github_command.arguments.body, /Disputed statement:/);
  assert.match(dispute.github_command.arguments.body, /Interim fail-closed effect:/);
  assert.equal(calls.length, 0);
});

test("identical input produces an identical command without storing state", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const args = { ...APPEND, operation: CommentChangeOperation.CORRECTION };
  assert.deepEqual(await call(args), await call(args));
  assert.equal(calls.length, 0);
});

test("ordinary deletion is denied and escalated to Strategy without a GitHub command", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const result = await call({
    ...BASE,
    operation: CommentChangeOperation.DELETE,
    deletion_reason: "ORDINARY",
  });

  assert.equal(result.decision, "PERMISSION_DENIED");
  assert.equal(result.policy, "AI_COMMENT_HISTORY_APPEND_ONLY");
  assert.equal(result.github_command, null);
  assert.equal(result.escalation.target, "STRATEGY");
  assert.equal(result.authoritative, false);
  assert.equal(calls.length, 0);
});

test("sensitive deletion requires founder break-glass without accepting or echoing content", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const result = await call({
    ...BASE,
    operation: CommentChangeOperation.DELETE,
    deletion_reason: "SENSITIVE_EXPOSURE",
  });

  assert.equal(result.decision, "FOUNDER_BREAK_GLASS_REQUIRED");
  assert.equal(result.github_command, null);
  assert.equal(result.escalation.target, "FOUNDER");
  assert.match(result.escalation.action, /Do not repeat/);
  assert.equal(calls.length, 0);

  const secret = "SECRET_VALUE_MUST_NOT_ESCAPE";
  await assert.rejects(
    call({
      ...BASE,
      operation: CommentChangeOperation.DELETE,
      deletion_reason: "SENSITIVE_EXPOSURE",
      prior_statement: secret,
    }),
    (error) => error.class === ErrorClass.INVALID_INPUT && !JSON.stringify(error.toJSON()).includes(secret)
  );
  assert.equal(calls.length, 0);
});

test("delete requests require an exact reason and append requests reject deletion fields", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const deletion_reason of [undefined, "", "OTHER", true]) {
    await assert.rejects(
      call({ ...BASE, operation: CommentChangeOperation.DELETE, deletion_reason }),
      (error) => error.class === ErrorClass.INVALID_INPUT
    );
  }
  await assert.rejects(
    call({ ...APPEND, operation: CommentChangeOperation.CORRECTION, deletion_reason: "ORDINARY" }),
    (error) => error.class === ErrorClass.INVALID_INPUT
  );
  assert.equal(calls.length, 0);
});

test("unknown operations and invalid identifiers fail closed", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const args of [
    { ...APPEND, operation: "EDIT" },
    { ...APPEND, operation: "correction" },
    { ...APPEND, operation: null },
    { ...APPEND, operation: CommentChangeOperation.CORRECTION, issue_number: 0 },
    { ...APPEND, operation: CommentChangeOperation.CORRECTION, issue_number: 1.5 },
    { ...APPEND, operation: CommentChangeOperation.CORRECTION, original_comment_id: "5578546622" },
  ]) {
    await assert.rejects(call(args), (error) => error.class === ErrorClass.INVALID_INPUT);
  }
  assert.equal(calls.length, 0);
});

test("append operations require every bounded structured field", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const field of ["prior_statement", "new_statement", "evidence_refs", "effect"]) {
    const args = { ...APPEND, operation: CommentChangeOperation.CORRECTION };
    delete args[field];
    await assert.rejects(call(args), (error) => error.class === ErrorClass.INVALID_INPUT, field);
  }
  for (const evidence_refs of [[], Array(MAX_EVIDENCE_REFS + 1).fill("evidence"), ["line one\nline two"]]) {
    await assert.rejects(
      call({ ...APPEND, operation: CommentChangeOperation.CORRECTION, evidence_refs }),
      (error) => error.class === ErrorClass.INVALID_INPUT
    );
  }
  assert.equal(calls.length, 0);
});

test("byte limits are enforced before any action is returned", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  await assert.rejects(
    call({
      ...APPEND,
      operation: CommentChangeOperation.CORRECTION,
      new_statement: "x".repeat(MAX_CHANGE_TEXT_BYTES + 1),
    }),
    (error) => error.class === ErrorClass.INVALID_INPUT
  );
  await assert.rejects(
    call({
      ...APPEND,
      operation: CommentChangeOperation.CORRECTION,
      evidence_refs: ["x".repeat(MAX_EVIDENCE_REF_BYTES + 1)],
    }),
    (error) => error.class === ErrorClass.INVALID_INPUT
  );
  await assert.rejects(
    call({
      ...APPEND,
      operation: CommentChangeOperation.CORRECTION,
      evidence_refs: Array(MAX_EVIDENCE_REFS).fill("x".repeat(MAX_EVIDENCE_REF_BYTES)),
    }),
    (error) => error.class === ErrorClass.INVALID_INPUT
  );
  assert.equal(calls.length, 0);
});

test("repository allowlist and unexpected-field denial happen without upstream access", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  await assert.rejects(
    callTool(ENV, "handle_comment_change_request", {
      ...APPEND,
      owner: "someone",
      repo: "else",
      operation: CommentChangeOperation.CORRECTION,
    }),
    (error) => error.class === ErrorClass.ALLOWLIST_DENIED
  );
  await assert.rejects(
    call({ ...APPEND, operation: CommentChangeOperation.CORRECTION, body: "caller-controlled body" }),
    (error) => error.class === ErrorClass.INVALID_INPUT && error.details.unexpected_fields[0] === "body"
  );
  assert.equal(calls.length, 0);
});

test("case variants of the policy tool name remain unreachable", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const name of ["HANDLE_COMMENT_CHANGE_REQUEST", "handle_Comment_change_request"]) {
    await assert.rejects(
      callTool(ENV, name, { ...APPEND, operation: CommentChangeOperation.CORRECTION }),
      (error) => error.class === ErrorClass.UNKNOWN_TOOL
    );
  }
  assert.equal(calls.length, 0);
});

test("results never contain edit, update, patch, or delete GitHub commands", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const results = [
    await call({ ...APPEND, operation: CommentChangeOperation.CORRECTION }),
    await call({ ...APPEND, operation: CommentChangeOperation.STATUS_UPDATE }),
    await call({ ...APPEND, operation: CommentChangeOperation.DISPUTE }),
    await call({ ...BASE, operation: CommentChangeOperation.DELETE, deletion_reason: "ORDINARY" }),
    await call({ ...BASE, operation: CommentChangeOperation.DELETE, deletion_reason: "SENSITIVE_EXPOSURE" }),
  ];

  for (const result of results) {
    const command = result.github_command;
    if (command) {
      assert.equal(command.capability, "add_issue_comment");
      assert.doesNotMatch(command.preferred_tool, /edit|update|delete|patch/i);
    }
    assert.equal(result.authorship_verified, false);
    assert.equal(result.original_comment_verified, false);
    assert.equal(result.authoritative, false);
  }
  assert.equal(calls.length, 0);
});

test("the real MCP transport dispatches the policy tool without a GitHub request", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const response = await rpc("tools/call", {
    name: "handle_comment_change_request",
    arguments: { ...APPEND, operation: CommentChangeOperation.CORRECTION },
  });
  const body = await response.json();
  const value = JSON.parse(body.result.content[0].text);

  assert.equal(response.status, 200);
  assert.equal(value.decision, "APPEND_COMMENT");
  assert.equal(value.github_command.capability, "add_issue_comment");
  assert.equal(calls.length, 0);
});

test("the policy module has no network or credential surface", () => {
  const source = readFileSync(new URL("../src/comment-change.js", import.meta.url), "utf8");
  for (const forbidden of [
    /\bfetch\s*\(/,
    /\bgh(?:Paginate)?\s*\(/,
    /GITHUB_TOKEN/,
    /MCP_ACCESS_TOKEN/,
    /method\s*:\s*["'](?:POST|PATCH|DELETE)["']/,
  ]) {
    assert.doesNotMatch(source, forbidden);
  }
});
