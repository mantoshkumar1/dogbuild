import { test } from "node:test";
import assert from "node:assert/strict";
import { assertRepoAllowed, assertWritableBranch, parseAllowlist } from "../src/allowlist.js";
import { callTool } from "../src/handlers.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, mockFetch } from "./helpers.mjs";

test("unset allowlist denies everything", () => {
  assert.throws(() => parseAllowlist({}), (e) => e.class === ErrorClass.CONFIG_INVALID);
  assert.throws(() => parseAllowlist({ ALLOWED_REPOS: "   " }), (e) => e.class === ErrorClass.CONFIG_INVALID);
});

test("malformed allowlist denies everything", () => {
  assert.throws(() => parseAllowlist({ ALLOWED_REPOS: "not-a-repo" }), (e) => e.class === ErrorClass.CONFIG_INVALID);
  assert.throws(() => parseAllowlist({ ALLOWED_REPOS: "a/b,,broken" }), (e) => e.class === ErrorClass.CONFIG_INVALID);
});

test("repository outside the allowlist is denied", () => {
  assert.throws(() => assertRepoAllowed(ENV, "someone", "else"), (e) => e.class === ErrorClass.ALLOWLIST_DENIED);
});

test("denial happens before any upstream request is issued", async () => {
  const calls = mockFetch();
  await assert.rejects(
    callTool(ENV, "get_repo", { owner: "someone", repo: "else" }, { role: "read" }),
    (e) => e.class === ErrorClass.ALLOWLIST_DENIED
  );
  assert.equal(calls.length, 0, "no GitHub request may be made for a denied repository");
});

test("protected branches can never be written", () => {
  for (const b of ["main", "MAIN", "staging", "master", "production"]) {
    assert.throws(() => assertWritableBranch(b, null), (e) => e.class === ErrorClass.BRANCH_DENIED);
  }
});

test("only the branch named in the role assertion may be written", () => {
  assert.equal(assertWritableBranch("db-164-work", "db-164-work"), "db-164-work");
  assert.throws(() => assertWritableBranch("other-branch", "db-164-work"), (e) => e.class === ErrorClass.BRANCH_DENIED);
});
