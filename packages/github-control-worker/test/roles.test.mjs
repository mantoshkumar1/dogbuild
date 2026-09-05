import { test } from "node:test";
import assert from "node:assert/strict";
import { resolveRole, signRoleAssertion, verifyRoleAssertion } from "../src/roles.js";
import { toolsForRole, TOOLS } from "../src/tools.js";
import { callTool } from "../src/handlers.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, SHA, mockFetch } from "./helpers.mjs";

const NOW = 1788600000000;
const base = (over = {}) => ({
  role: "implementor", task: "DB-164", repo: "mantoshkumar1/dogbuild",
  subject: "claude", nonce: "n1", exp: NOW + 600000, ...over,
});

test("no assertion means read-only, never a write role", async () => {
  const ctx = await resolveRole(ENV, null);
  assert.equal(ctx.role, "read");
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "create_pull_request", { owner: "mantoshkumar1", repo: "dogbuild", title: "t", head: "h", base: "b" }, ctx),
    (e) => e.class === ErrorClass.ROLE_DENIED
  );
  assert.equal(calls.length, 0);
});

test("a forged or tampered assertion is rejected", async () => {
  const good = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base());
  const [payload] = good.split(".");
  await assert.rejects(verifyRoleAssertion(ENV, `${payload}.wrongsignature`, NOW), (e) => e.class === ErrorClass.ROLE_DENIED);
  await assert.rejects(verifyRoleAssertion(ENV, "garbage", NOW), (e) => e.class === ErrorClass.ROLE_DENIED);
  const otherKey = await signRoleAssertion("attacker-key", base());
  await assert.rejects(verifyRoleAssertion(ENV, otherKey, NOW), (e) => e.class === ErrorClass.ROLE_DENIED);
});

test("expired or over-long assertions are rejected", async () => {
  const expired = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base({ exp: NOW - 1 }));
  await assert.rejects(verifyRoleAssertion(ENV, expired, NOW), (e) => e.class === ErrorClass.ROLE_DENIED);
  const tooLong = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base({ exp: NOW + 99 * 60 * 60 * 1000 }));
  await assert.rejects(verifyRoleAssertion(ENV, tooLong, NOW), (e) => e.class === ErrorClass.ROLE_DENIED);
});

test("assertions missing binding fields are rejected", async () => {
  for (const missing of ["task", "repo", "subject", "nonce"]) {
    const payload = base();
    delete payload[missing];
    const a = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, payload);
    await assert.rejects(verifyRoleAssertion(ENV, a, NOW), (e) => e.class === ErrorClass.ROLE_DENIED);
  }
});

test("a producer cannot hold reviewer authority over its own lineage", async () => {
  const a = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base({ role: "reviewer", subject: "claude", producer: "claude" }));
  await assert.rejects(verifyRoleAssertion(ENV, a, NOW), (e) => e.class === ErrorClass.SELF_REVIEW_DENIED);
  const ok = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base({ role: "reviewer", subject: "codex", producer: "claude" }));
  assert.equal((await verifyRoleAssertion(ENV, ok, NOW)).role, "reviewer");
});

test("no signing key configured means no role can be granted", async () => {
  const a = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base());
  await assert.rejects(verifyRoleAssertion({}, a, NOW), (e) => e.class === ErrorClass.CONFIG_INVALID);
});

test("an assertion cannot be replayed against another repository", async () => {
  const a = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base({ repo: "mantoshkumar1/dogbuild" }));
  const ctx = await resolveRole(ENV, a, NOW);
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "create_issue", { owner: "mantoshkumar1", repo: "pingstep", title: "t" }, ctx),
    (e) => e.class === ErrorClass.ROLE_DENIED
  );
  assert.equal(calls.length, 0);
});

test("a role named in tool arguments is ignored", async () => {
  const ctx = await resolveRole(ENV, null);
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "publish_review", { owner: "mantoshkumar1", repo: "pingstep", pull_number: 1, expected_head_sha: SHA, body: "x", role: "reviewer", profile: "reviewer" }, ctx),
    (e) => e.class === ErrorClass.ROLE_DENIED
  );
  assert.equal(calls.length, 0, "an argument-supplied role must not unlock anything");
});

test("profiles are disjoint where the design says they are", () => {
  const readNames = toolsForRole("read").map((t) => t.name);
  const implNames = toolsForRole("implementor").map((t) => t.name);
  const revNames = toolsForRole("reviewer").map((t) => t.name);
  assert.ok(!readNames.includes("update_issue_comment"), "read profile has no writes");
  assert.ok(!readNames.some((n) => implNames.includes(n) && !readNames.includes(n)));
  assert.ok(!implNames.includes("publish_review"), "an implementor cannot publish a review");
  assert.ok(!revNames.includes("create_or_update_file"), "a reviewer cannot write files");
  assert.ok(!revNames.includes("create_pull_request"), "a reviewer cannot open PRs");
  assert.ok(revNames.includes("publish_review") && revNames.includes("update_issue_comment"));
  for (const t of TOOLS) assert.ok(t.profiles.length > 0, `${t.name} must belong to a profile`);
});

test("an implementor cannot publish a review even with a valid assertion", async () => {
  const a = await signRoleAssertion(ENV.ROLE_ASSERTION_KEY, base({ repo: "mantoshkumar1/pingstep" }));
  const ctx = await resolveRole(ENV, a, NOW);
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "publish_review", { owner: "mantoshkumar1", repo: "pingstep", pull_number: 1, expected_head_sha: SHA, body: "x" }, ctx),
    (e) => e.class === ErrorClass.ROLE_DENIED
  );
  assert.equal(calls.length, 0);
});
