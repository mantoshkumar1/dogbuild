import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { OWNER, REPO, SHA, callRaw, installRoutes, smallFlow } from "./raw-support.mjs";

const bad = [
  { owner: OWNER, repo: REPO, sha: "A".repeat(40) },
  { owner: OWNER, repo: REPO, sha: "a".repeat(39) },
  { owner: OWNER, repo: REPO, sha: "a".repeat(41) },
  { owner: OWNER, repo: REPO, sha: `${"a".repeat(39)}g` },
  { owner: OWNER, repo: REPO, sha: ` ${"a".repeat(39)}` },
  { owner: OWNER, repo: REPO, sha: "main" },
  { owner: OWNER, repo: REPO, sha: 7 },
  { owner: OWNER, repo: REPO, sha: null },
  { owner: OWNER, repo: REPO },
  { owner: OWNER, sha: SHA },
  { repo: REPO, sha: SHA },
  { owner: OWNER, repo: REPO, sha: SHA, extra: "SENTINEL_SECRET_VALUE" },
  { owner: 1, repo: REPO, sha: SHA },
  { owner: OWNER, repo: {}, sha: SHA },
];

test("row 20: every malformed input is a fixed non-reflective error with zero GETs", async () => {
  for (const args of bad) {
    const calls = installRoutes(smallFlow().routes);
    const response = await callRaw(worker, args);
    const text = await response.text();
    const parsed = JSON.parse(text);
    assert.equal(response.status, 200);
    assert.equal(parsed.id, 1);
    assert.equal(parsed.error.data.error_class, "INVALID_INPUT");
    if (parsed.error.data.reason !== undefined) assert.match(parsed.error.data.reason, /^(INVALID_ARGUMENTS|INVALID_SHA)$/);
    else assert.match(parsed.error.message, /is not a valid GitHub repository component\.$/);
    assert.equal(calls.length, 0);
    assert.ok(!text.includes("SENTINEL_SECRET_VALUE"));
  }
});

test("row 20: non-object arguments are rejected the same way", async () => {
  for (const raw of ["null", "[]", '"x"', "1", "true"]) {
    const calls = installRoutes({});
    const body = `{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_raw_commit","arguments":${raw}}}`;
    const parsed = await (await callRaw(worker, null, { rawBody: body })).json();
    assert.equal(parsed.error.data.reason, "INVALID_ARGUMENTS");
    assert.equal(calls.length, 0);
  }
});

test("row 20: a lowercase 40-hex sha is accepted and reaches the first GET exactly", async () => {
  const calls = installRoutes(smallFlow().routes);
  const parsed = await (await callRaw(worker, { owner: OWNER, repo: REPO, sha: SHA })).json();
  assert.equal(parsed.error, undefined);
  assert.ok(String(calls[0].url ?? calls[0]).endsWith(`/git/commits/${SHA}`));
});
