import { test } from "node:test";
import assert from "node:assert/strict";
import { assertRepoAllowed, parseAllowlist } from "../src/allowlist.js";
import { callTool } from "../src/handlers.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, SHA, mockFetch } from "./helpers.mjs";

test("an unset or malformed allowlist denies every repository", () => {
  for (const value of [
    undefined,
    "",
    " ",
    "not-a-repository",
    "owner/repo,broken",
    "owner/repo,",
    ",owner/repo",
    "owner/repo,,other/repo",
    "../repo",
    "owner/../repo",
  ]) {
    assert.throws(
      () => parseAllowlist(value === undefined ? {} : { ALLOWED_REPOS: value }),
      (error) => error.class === ErrorClass.CONFIG_INVALID
    );
  }
});

test("allowlist matching is case-insensitive and returns the requested canonical parts", () => {
  assert.deepEqual(
    assertRepoAllowed({ ALLOWED_REPOS: "MantoshKumar1/PingStep" }, "mantoshkumar1", "pingstep"),
    { owner: "mantoshkumar1", repo: "pingstep", fullName: "mantoshkumar1/pingstep" }
  );
});

test("a repository outside the allowlist fails before GitHub access", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  await assert.rejects(
    callTool(ENV, "get_commit_ci", { owner: "someone", repo: "else", sha: SHA }),
    (error) => error.class === ErrorClass.ALLOWLIST_DENIED
  );
  assert.equal(calls.length, 0);
});

test("malformed repository components fail before GitHub access", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const args of [
    { owner: "a/b", repo: "pingstep", sha: SHA },
    { owner: "mantoshkumar1", repo: "..", sha: SHA },
    { owner: "", repo: "pingstep", sha: SHA },
  ]) {
    await assert.rejects(callTool(ENV, "get_commit_ci", args), (error) => error.class === ErrorClass.INVALID_INPUT);
  }
  assert.equal(calls.length, 0);
});

test("unexpected arguments are refused before allowlist or GitHub access", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  await assert.rejects(
    callTool(ENV, "get_commit_ci", { owner: "mantoshkumar1", repo: "pingstep", sha: SHA, branch: "main" }),
    (error) => error.class === ErrorClass.INVALID_INPUT && error.details.unexpected_fields[0] === "branch"
  );
  assert.equal(calls.length, 0);
});
