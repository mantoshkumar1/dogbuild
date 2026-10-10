import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { ENV, OWNER, REPO, SHA, callRaw, installRoutes, smallFlow } from "./raw-support.mjs";

test("row 22: disallowed repositories get a fixed ALLOWLIST_DENIED error and zero GETs", async () => {
  for (const [owner, repo] of [["someone", "else"], [OWNER, "other"], [OWNER, `${REPO}2`]]) {
    const calls = installRoutes(smallFlow().routes);
    const text = await (await callRaw(worker, { owner, repo, sha: SHA })).text();
    const parsed = JSON.parse(text);
    assert.equal(parsed.error.data.error_class, "ALLOWLIST_DENIED");
    assert.equal(parsed.error.data.reason, "REPOSITORY_NOT_ALLOWED");
    assert.equal(calls.length, 0);
    assert.ok(!text.includes(owner === OWNER ? "@@@" : owner));
    assert.ok(!text.includes(ENV.GITHUB_TOKEN));
  }
});

test("row 22: an unset or empty allowlist fails closed with zero GETs", async () => {
  for (const ALLOWED_REPOS of ["", undefined]) {
    const calls = installRoutes(smallFlow().routes);
    const env = { ...ENV, ALLOWED_REPOS };
    const response = await callRaw(worker, { owner: OWNER, repo: REPO, sha: SHA }, { env });
    assert.equal(response.status, 503);
    assert.equal(await response.text(), "Server unavailable");
    assert.equal(calls.length, 0);
  }
});

test("row 25: requests only ever target the allowlisted repository's git endpoints with GET", async () => {
  const calls = installRoutes(smallFlow().routes);
  await (await callRaw(worker, { owner: OWNER, repo: REPO, sha: SHA })).text();
  assert.equal(calls.length, 3);
  for (const call of calls) {
    const url = String(call.url ?? call);
    assert.ok(url.startsWith(`https://api.github.com/repos/${OWNER}/${REPO}/git/`), url);
    assert.equal((call.method ?? call.init?.method ?? "GET").toUpperCase(), "GET");
  }
});
