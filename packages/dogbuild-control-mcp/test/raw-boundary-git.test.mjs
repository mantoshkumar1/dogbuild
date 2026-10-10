import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import worker from "../src/index.js";
import { getRawCommit } from "../src/raw-commit.js";
import { jsonUtf8Length } from "../src/output.js";
import {
  ENV, GIT, OWNER, REPO, SHA, callRaw, chunkedResponse, commitBody, generateGitFixture, gitAvailable,
  independentVerify, installRoutes, jsonResponse, treeBody,
} from "./raw-support.mjs";

const MAX = 524_288;
const CAP = 2_097_152;
const CHUNK = 65_536;
const EMPTY = "4b825dc642cb6eb9a060e54bf8d69288fbee4904";
const enc = new TextEncoder();
const sha256 = (value) => createHash("sha256").update(value).digest("hex");

// Genuine Git objects are required; the suite fails closed if git is missing.
test("git is available (the boundary fixtures fail closed otherwise)", () => {
  assert.equal(gitAvailable(), true);
});

// Accepted R355/R356 pins (mantoshkumar1/dogbuild#164 comments 6063494884 + 6063497751).
// Fixture A content is unchanged from R353; fixture B is the R355 replacement (L1=122, L2=127).
// The 170 ordered parents do not depend on the tree, so A and B share one list. It is pinned by
// count, first, last and the SHA-256 of the newline-joined ordered list (any reorder/change fails).
const PARENT_COUNT = 170;
const PARENT_FIRST = "1dfc41dd73aa729d2aeb0b2896cccd9353717219";
const PARENT_LAST = "424aed31ef0e3bfe20c4d12a101f1a0c4ad45267";
const PARENTS_SHA256 = "423034cb673e8a18622f6984197c0f006cd7a88978287c715695238512d985f7";

const PINS = {
  A: {
    L1: 100, L2: 100,
    tree: "32ad195e7dc34e81c76b32ced5320b039c07ae8c",
    commit: "97489121fe43af26b4b527785b326fc87b427471",
    encoded: 831_034,
    sha256: "313a61297b24d750be89ef6d4db48d75636bc2c644711f31d68e395fd812eeaf",
    recTwoSpace: 1_768_208, recCompact: 1_544_188, rootTwoSpace: 352_208, rootCompact: 302_188,
    marginTwoSpace: 328_944, marginCompact: 552_964,
    recHash: "dcd1efa61129b234104e6aa591f4bbb3f60109f4a4b3e3645886b3345e079e76",
    rootHash: "020f0aeaa8f0bc46a05b7b83732e48cffdecd8c84f286244a581570974fc546c",
    degraded: 8192,
  },
  B: {
    L1: 122, L2: 127,
    tree: "91872b1ea16d1ae7d2c87aed60dd32b3deeb0c0b",
    commit: "906d7ab036de24048075cf177450f1271d0e19ca",
    encoded: 1_000_034,
    sha256: "2159d1c925d2d0b8331c3a40f7d395e91bfedbb8e7709340f2623ffa34edd98b",
    recTwoSpace: 1_937_208, recCompact: 1_713_188, rootTwoSpace: 374_208, rootCompact: 324_188,
    marginTwoSpace: 159_944, marginCompact: 383_964,
    recHash: "a400c0046f8892baa288815cb438f4bb868e7defcdb1c0587a8add86e6474128",
    rootHash: "88c2ed2adfaea7c944c987fbe66e75d137be82416091a2784ac5f161b8c51156",
    degraded: 8193,
  },
};
// Superseded R353 fixture B (L=150/150): its genuine ordinary two-space recursive body is over the cap.
const OLD_B = { L: 150, tree: "50f7de126ffef55b4f09995394bd0f43321efc52", recTwoSpace: 2_118_208 };
const COUNTS = { root_entry_count: 1000, recursive_entry_count: 4000, tree_count: 1000, blob_count: 3000, submodule_count: 0, subtree_hashes_verified: 1000 };

// Each fixture is generated once with real git and shared by the tests below.
const memo = new Map();
function fixture(key, L1, L2) {
  if (!memo.has(key)) memo.set(key, generateGitFixture({ L1, L2, parents: 170 }));
  return memo.get(key);
}

function bodiesOf(fx) {
  const top = fx.entries.filter((e) => !e.path.includes("/"));
  const root = treeBody(fx.tree, top);
  const rec = treeBody(fx.tree, fx.entries);
  const bytes = (obj, space) => enc.encode(JSON.stringify(obj, null, space));
  return {
    rootTwo: bytes(root, 2), rootCompact: bytes(root, undefined),
    recTwo: bytes(rec, 2), recCompact: bytes(rec, undefined),
  };
}

/** Raw-byte response: delivered in 64 KiB chunks; counts the bytes the production reader consumed. */
function rawResponse(body, counter) {
  let offset = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (offset >= body.length) { controller.close(); return; }
      const chunk = body.subarray(offset, Math.min(body.length, offset + CHUNK));
      offset += chunk.length;
      counter.delivered += chunk.length;
      controller.enqueue(chunk);
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "application/json; charset=utf-8" } });
}

/** Install the three routes of an honest flow with exact raw bodies. Returns counters + calls. */
function installRaw(fx, bodies, form) {
  const counters = { root: { delivered: 0 }, rec: { delivered: 0 } };
  const rootBody = form === "compact" ? bodies.rootCompact : bodies.rootTwo;
  const recBody = form === "compact" ? bodies.recCompact : bodies.recTwo;
  const calls = installRoutes({
    [`${GIT}/commits/${fx.commit}`]: jsonResponse(commitBody(fx.commit, fx.tree, fx.parents)),
    [`${GIT}/trees/${fx.tree}`]: () => rawResponse(rootBody, counters.root),
    [`${GIT}/trees/${fx.tree}?recursive=1`]: () => rawResponse(recBody, counters.rec),
  });
  return { calls, counters, rootBody, recBody };
}

function assertGeneratorPins(fx, pin) {
  assert.equal(fx.tree, pin.tree);
  assert.equal(fx.readTree, pin.tree);
  assert.equal(fx.commit, pin.commit);
  assert.equal(fx.parents.length, PARENT_COUNT);
  assert.equal(fx.parents[0], PARENT_FIRST);
  assert.equal(fx.parents[PARENT_COUNT - 1], PARENT_LAST);
  assert.equal(new Set(fx.parents).size, PARENT_COUNT);
  assert.equal(sha256(fx.parents.join("\n")), PARENTS_SHA256);
  assert.equal(fx.revList, [fx.commit, ...fx.parents].join(" "));
  assert.equal(fx.entries.length, 4000);
  const verdict = independentVerify(fx.entries, fx.tree);
  assert.equal(verdict.ok, true);
  assert.equal(verdict.verified, 1000);
}

function assertBodyPins(bodies, pin) {
  assert.equal(bodies.recTwo.length, pin.recTwoSpace);
  assert.equal(bodies.recCompact.length, pin.recCompact);
  assert.equal(bodies.rootTwo.length, pin.rootTwoSpace);
  assert.equal(bodies.rootCompact.length, pin.rootCompact);
  assert.equal(CAP - bodies.recTwo.length, pin.marginTwoSpace);
  assert.equal(CAP - bodies.recCompact.length, pin.marginCompact);
  assert.ok(CAP - bodies.recTwo.length >= pin.marginTwoSpace);
  assert.ok(CAP - bodies.recCompact.length >= pin.marginCompact);
  assert.equal(sha256(bodies.recTwo), pin.recHash);
  assert.equal(sha256(bodies.rootTwo), pin.rootHash);
}

/** Full production path: raw bytes -> bounded reader -> parser -> verification -> COMPLETE primary -> buildDegraded. */
async function production(fx, bodies, form, pin) {
  const { counters, calls, rootBody, recBody } = installRaw(fx, bodies, form);
  const result = await getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: fx.commit });
  assert.equal(calls.length, 3);
  assert.equal(counters.root.delivered, rootBody.length);
  assert.equal(counters.rec.delivered, recBody.length);
  const { primary, degraded } = result;
  assert.equal(primary.status, "COMPLETE");
  assert.equal(primary.complete, true);
  assert.equal(primary.sha, fx.commit);
  assert.equal(primary.tree_sha, pin.tree);
  assert.deepEqual(primary.parents, fx.parents);
  assert.equal(sha256(primary.parents.join("\n")), PARENTS_SHA256);
  assert.equal(primary.parent_count, 170);
  assert.equal(primary.parents_duplicate_present, false);
  for (const [key, value] of Object.entries(COUNTS)) assert.equal(primary.tree_proof[key], value);
  assert.equal(primary.tree_proof.entries.length, 4000);
  assert.equal(primary.tree_proof.entries_encoded_bytes, pin.encoded);
  assert.equal(primary.tree_proof.entries_sha256, pin.sha256);
  assert.notEqual(degraded, null);
  assert.equal(degraded.tree_proof.entries, null);
  assert.equal(degraded.tree_proof.entries_encoded_bytes, pin.encoded);
  assert.equal(degraded.tree_proof.entries_sha256, pin.sha256);
  return { primary, degraded, measured: jsonUtf8Length(degraded) };
}

async function endToEnd(fx, bodies, form) {
  installRaw(fx, bodies, form);
  const response = await callRaw(worker, { owner: OWNER, repo: REPO, sha: fx.commit });
  const text = await response.text();
  assert.ok(enc.encode(text).length <= MAX);
  return { text, parsed: JSON.parse(text) };
}

for (const key of ["A", "B"]) {
  const pin = PINS[key];
  test(`row 24a: fixture ${key} - real git generator reproduces every pinned tree, commit, ordered parent and raw-body size/hash/margin`, { timeout: 120_000 }, () => {
    const fx = fixture(key, pin.L1, pin.L2);
    assertGeneratorPins(fx, pin);
    assertBodyPins(bodiesOf(fx), pin);
  });

  for (const form of ["twoSpace", "compact"]) {
    test(`row 24a: fixture ${key} ${form} raw bodies traverse the production bounded reader to a verified COMPLETE primary, then buildDegraded measures exactly ${pin.degraded}`, { timeout: 120_000 }, async () => {
      const fx = fixture(key, pin.L1, pin.L2);
      const bodies = bodiesOf(fx);
      const { measured } = await production(fx, bodies, form === "compact" ? "compact" : "two", pin);
      assert.equal(measured, pin.degraded);
    });
  }
}

test("row 24a: fixture A (tier-2 accept) - end to end the degraded form of 8,192 bytes is returned", { timeout: 120_000 }, async () => {
  const fx = fixture("A", PINS.A.L1, PINS.A.L2);
  const { parsed } = await endToEnd(fx, bodiesOf(fx), "two");
  const value = JSON.parse(parsed.result.content[0].text);
  assert.equal(value.status, "INCOMPLETE");
  assert.equal(value.incomplete_reason, "OUTPUT_CEILING_EXCEEDED");
  assert.equal(value.complete, false);
  assert.equal(value.tree_proof.entries, null);
  assert.equal(value.tree_proof.entries_encoded_bytes, PINS.A.encoded);
  assert.equal(value.tree_proof.entries_sha256, PINS.A.sha256);
  assert.deepEqual(value.parents, fx.parents);
  assert.equal(enc.encode(parsed.result.content[0].text).length, PINS.A.degraded);
});

test("row 24a: fixture B (tier-3 reject) - degraded would be 8,193 bytes so the fixed same-ID error is returned", { timeout: 120_000 }, async () => {
  const fx = fixture("B", PINS.B.L1, PINS.B.L2);
  const { parsed, text } = await endToEnd(fx, bodiesOf(fx), "two");
  assert.equal(parsed.id, 1);
  assert.equal(parsed.result, undefined);
  assert.equal(parsed.error.data.reason, "OUTPUT_CEILING_EXCEEDED");
  assert.ok(!text.includes(PINS.B.sha256));
});

test("row 24a: the genuine superseded R353 fixture B recursive body (2,118,208 bytes) fails closed as RESPONSE_TOO_LARGE before any COMPLETE primary or buildDegraded", { timeout: 120_000 }, async () => {
  const fx = fixture("oldB", OLD_B.L, OLD_B.L);
  assert.equal(fx.tree, OLD_B.tree);
  const bodies = bodiesOf(fx);
  assert.equal(bodies.recTwo.length, OLD_B.recTwoSpace);
  assert.ok(bodies.recTwo.length > CAP);
  assert.equal(bodies.recTwo.length - CAP, 21_056);
  const { counters } = installRaw(fx, bodies, "two");
  const result = await getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: fx.commit });
  assert.equal(result.primary.status, "INCOMPLETE");
  assert.equal(result.primary.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(result.primary.tree_proof, null);
  assert.equal(result.degraded, null);
  // the bounded reader stopped streaming at the cap instead of consuming the whole body
  assert.ok(counters.rec.delivered < bodies.recTwo.length + 1);
  assert.ok(counters.rec.delivered >= CAP);
});

test("row 24a: fixture B padded with trailing whitespace passes at exactly 2,097,152 bytes and fails closed at 2,097,153", { timeout: 120_000 }, async () => {
  const fx = fixture("B", PINS.B.L1, PINS.B.L2);
  const bodies = bodiesOf(fx);
  const padded = (size) => {
    const out = new Uint8Array(size);
    out.fill(0x20);
    out.set(bodies.recTwo, 0);
    return out;
  };
  const run = async (size) => {
    installRaw(fx, { ...bodies, recTwo: padded(size) }, "two");
    return getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: fx.commit });
  };
  const at = await run(CAP);
  assert.equal(at.primary.status, "COMPLETE");
  assert.equal(at.primary.tree_proof.entries_sha256, PINS.B.sha256);
  assert.equal(jsonUtf8Length(at.degraded), PINS.B.degraded);
  const above = await run(CAP + 1);
  assert.equal(above.primary.status, "INCOMPLETE");
  assert.equal(above.primary.incomplete_reason, "RESPONSE_TOO_LARGE");
  assert.equal(above.degraded, null);
});

// Retained from the first producer head: a synthetic padded JSON string (not a tree object) is never COMPLETE.
test("row 24a: the superseded 2,118,208-byte recursive body fails closed; cap padding passes at 2,097,152 and fails at 2,097,153", async () => {
  const run = async (size) => {
    const filler = "x".repeat(Math.max(0, size - 2));
    const body = `"${filler}"`; // one JSON string of exactly `size` bytes
    installRoutes({
      [`${GIT}/commits/${SHA}`]: jsonResponse(commitBody(SHA, "4b825dc642cb6eb9a060e54bf8d69288fbee4904", [])),
      [`${GIT}/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904`]: jsonResponse(treeBody("4b825dc642cb6eb9a060e54bf8d69288fbee4904", [])),
      [`${GIT}/trees/4b825dc642cb6eb9a060e54bf8d69288fbee4904?recursive=1`]: () => chunkedResponse([new TextEncoder().encode(body)], { headers: { "content-type": "application/json" } }),
    });
    const response = await callRaw(worker, { owner: OWNER, repo: REPO, sha: SHA });
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
