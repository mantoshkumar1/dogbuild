import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import {
  GIT, OWNER, REPO, SHA, callRaw, chunkedResponse, flowRoutes, generateGitFixture, gitAvailable, independentVerify, installRoutes, jsonResponse, treeBody, commitBody,
} from "./raw-support.mjs";

const ARGS = { owner: OWNER, repo: REPO, sha: SHA };
const MAX = 524_288;
const CAP = 2_097_152;

// Genuine Git objects are required; the suite fails closed if git is missing.
test("git is available (the boundary fixtures fail closed otherwise)", () => {
  assert.equal(gitAvailable(), true);
});

const PINS = {
  A: { L: 100, tree: "32ad195e7dc34e81c76b32ced5320b039c07ae8c", sha256: "313a61297b24d750be89ef6d4db48d75636bc2c644711f31d68e395fd812eeaf", encoded: 831_034, degraded: 8192 },
  B: { L: 150, tree: "50f7de126ffef55b4f09995394bd0f43321efc52", sha256: "bd004f87e5bee8ba96670fde05e30811ade63483b47b4775d1fca04ee3378cb0", encoded: 1_181_034, degraded: 8193 },
};

async function boundary(pin) {
  const fx = generateGitFixture({ L1: pin.L, L2: pin.L, parents: 170 });
  assert.equal(fx.tree, pin.tree);
  assert.equal(fx.readTree, pin.tree);
  assert.equal(fx.entries.length, 4000);
  assert.equal(fx.parents.length, 170);
  const verdict = independentVerify(fx.entries, fx.tree);
  assert.equal(verdict.ok, true);
  assert.equal(verdict.verified, 1000);
  const routes = flowRoutes({ sha: SHA, treeSha: fx.tree, parents: fx.parents, entries: fx.entries });
  const calls = installRoutes(routes);
  const response = await callRaw(worker, ARGS);
  const text = await response.text();
  assert.equal(calls.length, 3);
  assert.ok(new TextEncoder().encode(text).length <= MAX);
  return { fx, response, text, parsed: JSON.parse(text) };
}

test("row 24a: fixture A (tier-2 accept) - real git objects, exact digest, degraded form of 8,192 bytes", { timeout: 120_000 }, async () => {
  const { parsed } = await boundary(PINS.A);
  const value = JSON.parse(parsed.result.content[0].text);
  assert.equal(value.status, "INCOMPLETE");
  assert.equal(value.incomplete_reason, "OUTPUT_CEILING_EXCEEDED");
  assert.equal(value.complete, false);
  assert.equal(value.tree_proof.entries, null);
  assert.equal(value.tree_proof.entries_encoded_bytes, PINS.A.encoded);
  assert.equal(value.tree_proof.entries_sha256, PINS.A.sha256);
  assert.equal(value.parents.length, 170);
  assert.equal(new TextEncoder().encode(parsed.result.content[0].text).length, PINS.A.degraded);
});

test("row 24a: fixture B (tier-3 reject) - degraded would be 8,193 bytes so the fixed same-ID error is returned", { timeout: 120_000 }, async () => {
  const { parsed, text } = await boundary(PINS.B);
  assert.equal(parsed.id, 1);
  assert.equal(parsed.result, undefined);
  assert.equal(parsed.error.data.reason, "OUTPUT_CEILING_EXCEEDED");
  assert.ok(!text.includes(PINS.B.sha256));
});

test("row 24a: the superseded 2,118,208-byte recursive body fails closed; cap padding passes at 2,097,152 and fails at 2,097,153", async () => {
  const run = async (size) => {
    const filler = "x".repeat(Math.max(0, size - 2));
    const body = `"${filler}"`; // one JSON string of exactly `size` bytes
    installRoutes({
      [`${GIT}/commits/${SHA}`]: jsonResponse(commitBody(SHA, "4b825dc642cb6eb9a060e54bf8d69288fbee4904", [])),
      [`${GIT}/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904`]: jsonResponse(treeBody("4b825dc642cb6eb9a060e54bf8d69288fbee4904", [])),
      [`${GIT}/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904?recursive=1`]: () => chunkedResponse([new TextEncoder().encode(body)], { headers: { "content-type": "application/json" } }),
    });
    const response = await callRaw(worker, ARGS);
    return JSON.parse((await response.text()));
  };
  const over = await run(2_118_208);
  const at = await run(CAP);
  const above = await run(CAP + 1);
  const reason = (p) => (p.result ? JSON.parse(p.result.content[0].text) : p.error?.data);
  // a bare padded string is not a tree object: never COMPLETE in any case
  for (const p of [over, at, above]) assert.notEqual(reason(p)?.status, "COMPLETE");
  assert.equal(reason(over).incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(reason(above).incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.notEqual(reason(at).incomplete_reason, "RESPONSE_TOO_LARGE");
});
