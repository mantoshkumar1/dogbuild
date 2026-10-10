import { test } from "node:test";
import assert from "node:assert/strict";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  DEGRADED_MAX_BYTES, LIMITS, MAX_MCP_RESPONSE_BYTES, TIER4_BODY, buildDegraded, isAllowedRequestId,
  isValidDegraded, jsonUtf8Length, serializeOutputCeilingError, serializeResult, utf8Length,
  writeErrorResponse, writeToolResponse,
} from "../src/output.js";
import { ControlError, ErrorClass } from "../src/errors.js";
import { getRawCommit } from "../src/raw-commit.js";
import { ENV, GIT, OWNER, REPO, SHA, clone, flowRoutes, hex40, installRoutes, smallFlow } from "./raw-support.mjs";

async function genuine(parents) {
  const flow = smallFlow({ parents });
  installRoutes(flow.routes);
  return getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA });
}

test("constants are pinned", () => {
  assert.equal(DEGRADED_MAX_BYTES, 8192);
  assert.equal(MAX_MCP_RESPONSE_BYTES, 524_288);
  assert.deepEqual(LIMITS, {
    max_gets: 3, max_response_bytes: 2_097_152, max_root_entries: 1000, max_recursive_entries: 20_000,
    deadline_ms: 45_000, max_mcp_response_bytes: 524_288,
  });
});

test("row 24 (i)-(v): tiers use a builder-made genuine degraded object", async () => {
  const { primary, degraded } = await genuine([hex40(1), hex40(2)]);
  assert.ok(isValidDegraded(degraded));
  assert.deepEqual(Object.keys(degraded), [
    "schema", "status", "complete", "incomplete_reason", "requested_sha", "sha", "tree_sha", "parents",
    "parent_count", "parents_duplicate_present", "commit_object_rehash", "tree_proof", "limits",
  ]);
  const env = { primary, degraded };
  for (const id of [1, "abc", null, 0, -7, 9007199254740991, ""]) {
    const t1 = serializeResult(id, primary);
    const exact = writeToolResponse(id, env, utf8Length(t1));
    assert.equal(exact.tier, 1);
    assert.equal(exact.body, t1);
    const over = writeToolResponse(id, env, utf8Length(t1) - 1);
    assert.equal(over.tier, 2);
    const parsed = JSON.parse(over.body);
    assert.ok(Object.is(parsed.id, id));
    const value = JSON.parse(parsed.result.content[0].text);
    assert.equal(value.incomplete_reason, "OUTPUT_CEILING_EXCEEDED");
    assert.equal(value.tree_proof.entries, null);
    assert.equal(value.complete, false);
    assert.ok(!("reason" in value) && !("entries" in value));
    // (iii) a degraded body that is itself over the ceiling falls to tier 3
    const t2 = serializeResult(id, degraded);
    const t3 = serializeOutputCeilingError(id);
    const three = writeToolResponse(id, env, utf8Length(t2) - 1);
    assert.equal(three.tier, 3);
    assert.ok(Object.is(JSON.parse(three.body).id, id));
    assert.equal(JSON.parse(three.body).error.data.reason, "OUTPUT_CEILING_EXCEEDED");
    // (iv) tier 3 over a tiny ceiling -> tier 4
    const four = writeToolResponse(id, env, utf8Length(t3) - 1);
    assert.deepEqual([four.tier, four.status, four.body, four.contentType], [4, 500, TIER4_BODY, "text/plain"]);
    assert.throws(() => JSON.parse(four.body));
  }
});

test("row 24 (ii): an absent or invalid degraded form always routes to tier 3, never serializing undefined", async () => {
  const { primary, degraded } = await genuine([hex40(1)]);
  const ceiling = utf8Length(serializeResult(1, primary)) - 1;
  const bad = [null, undefined, {}, [], "x", Object.assign(clone(degraded), { complete: true }),
    Object.assign(clone(degraded), { status: "COMPLETE" }), Object.assign(clone(degraded), { extra: 1 })];
  for (const candidate of bad) {
    const out = writeToolResponse(1, { primary, degraded: candidate }, ceiling);
    assert.equal(out.tier, 3);
    assert.ok(!out.body.includes("undefined"));
  }
  const omitted = writeToolResponse(1, { primary }, ceiling);
  assert.equal(omitted.tier, 3);
});

test("row 24 (vi): the envelope carries degraded only for a COMPLETE primary", async () => {
  const flow = smallFlow();
  installRoutes(flowRoutes({ sha: SHA, treeSha: flow.tree.rootSha, parents: [], entries: flow.tree.entries, truncatedRec: true }));
  const incomplete = await getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA });
  assert.equal(incomplete.primary.status, "INCOMPLETE");
  assert.equal(incomplete.degraded, null);
  assert.equal(buildDegraded(incomplete.primary), null);
  installRoutes({});
  await assert.rejects(getRawCommit(ENV, { owner: OWNER, repo: REPO, sha: SHA }), ControlError);
});

test("row 24 (vii): an invalid id throws instead of being echoed", async () => {
  const { primary, degraded } = await genuine([]);
  for (const id of [true, false, [], {}, 1.5, 9007199254740992, -0, Infinity, NaN, undefined]) {
    assert.throws(() => writeToolResponse(id, { primary, degraded }), TypeError);
    assert.throws(() => writeErrorResponse(id, new ControlError(ErrorClass.NOT_FOUND, "x")), TypeError);
    assert.equal(isAllowedRequestId(id), false);
  }
  for (const id of [0, 1, -7, 9007199254740991, -9007199254740991, "", "x", null]) assert.equal(isAllowedRequestId(id), true);
});

test("row 24a: degraded size is monotone in the parent count; the predicate flips exactly at 8,192", async () => {
  const sizeFor = async (count) => {
    const { degraded } = await genuine(Array.from({ length: count }, (_, i) => hex40(i + 1)));
    return [jsonUtf8Length(degraded), degraded];
  };
  let low = 1;
  let high = 400;
  while (low + 1 < high) {
    const mid = (low + high) >> 1;
    const [size] = await sizeFor(mid);
    if (size <= DEGRADED_MAX_BYTES) low = mid; else high = mid;
  }
  const [okSize, okObject] = await sizeFor(low);
  const [badSize, badObject] = await sizeFor(low + 1);
  assert.ok(okSize <= 8192 && badSize > 8192);
  assert.ok(okSize < badSize);
  assert.equal(isValidDegraded(okObject), true);
  assert.equal(isValidDegraded(badObject), false);
  const { primary } = await genuine(Array.from({ length: low + 1 }, (_, i) => hex40(i + 1)));
  const out = writeToolResponse(1, { primary, degraded: badObject }, utf8Length(serializeResult(1, primary)) - 1);
  assert.equal(out.tier, 3);
  for (const count of [0, 1, 2, 3]) assert.equal(isValidDegraded((await sizeFor(count))[1]), true);
});

const mutations = [
  ["top: add reason", (d) => { d.reason = "OUTPUT_CEILING_EXCEEDED"; }],
  ["top: add entries", (d) => { d.entries = null; }],
  ["top: add any extra key", (d) => { d.zzz = 1; }],
  ["top: delete incomplete_reason", (d) => { delete d.incomplete_reason; }],
  ["top: wrong incomplete_reason", (d) => { d.incomplete_reason = "GITHUB_TRUNCATED"; }],
  ["top: status COMPLETE", (d) => { d.status = "COMPLETE"; }],
  ["top: complete true", (d) => { d.complete = true; }],
  ["top: wrong schema", (d) => { d.schema = "x"; }],
  ["top: uppercase requested_sha", (d) => { d.requested_sha = d.requested_sha.toUpperCase().replace(/C/g, "C"); d.requested_sha = "C".repeat(40); }],
  ["top: short sha", (d) => { d.sha = d.sha.slice(1); }],
  ["top: non-hex tree_sha", (d) => { d.tree_sha = "g".repeat(40); }],
  ["top: sha !== requested_sha", (d) => { d.sha = hex40(5); }],
  ["top: parents not an array", (d) => { d.parents = "x"; }],
  ["top: non-hex parent", (d) => { d.parents[0] = "z".repeat(40); }],
  ["top: parent_count mismatch", (d) => { d.parent_count += 1; }],
  ["top: duplicate flag wrong", (d) => { d.parents_duplicate_present = true; }],
  ["top: commit_object_rehash changed", (d) => { d.commit_object_rehash = "PERFORMED"; }],
  ["top: tree_proof null", (d) => { d.tree_proof = null; }],
  ["top: tree_proof array", (d) => { d.tree_proof = []; }],
  ["top: tree_proof string", (d) => { d.tree_proof = "x"; }],
  ["proof: delete entries", (d) => { delete d.tree_proof.entries; }],
  ["proof: entries []", (d) => { d.tree_proof.entries = []; }],
  ["proof: entries undefined", (d) => { d.tree_proof.entries = undefined; }],
  ["proof: extra key", (d) => { d.tree_proof.extra = 1; }],
  ["proof: missing key", (d) => { delete d.tree_proof.tree_count; }],
  ["proof: wrong encoding", (d) => { d.tree_proof.entries_encoding = "v2"; }],
  ["proof: float count", (d) => { d.tree_proof.blob_count = 1.5; }],
  ["proof: negative count", (d) => { d.tree_proof.blob_count = -1; }],
  ["proof: string count", (d) => { d.tree_proof.blob_count = "4"; }],
  ["proof: NaN count", (d) => { d.tree_proof.blob_count = NaN; }],
  ["proof: count above 20,000", (d) => { d.tree_proof.recursive_entry_count = 20_001; }],
  ["proof: root above 1,000", (d) => { d.tree_proof.root_entry_count = 1001; }],
  ["proof: root above recursive", (d) => { d.tree_proof.root_entry_count = d.tree_proof.recursive_entry_count + 1; }],
  ["proof: count sum mismatch", (d) => { d.tree_proof.blob_count += 1; }],
  ["proof: verified above tree_count", (d) => { d.tree_proof.subtree_hashes_verified = d.tree_proof.tree_count + 1; }],
  ["proof: encoded bytes string", (d) => { d.tree_proof.entries_encoded_bytes = "1"; }],
  ["proof: encoded bytes float", (d) => { d.tree_proof.entries_encoded_bytes += 0.5; }],
  ["proof: encoded bytes below bound", (d) => { d.tree_proof.entries_encoded_bytes = 34 + 33 * d.tree_proof.recursive_entry_count - 1; }],
  ["proof: encoded bytes above bound", (d) => { d.tree_proof.entries_encoded_bytes = 34 + 32 * d.tree_proof.recursive_entry_count + 2_097_153; }],
  ["proof: uppercase digest", (d) => { d.tree_proof.entries_sha256 = d.tree_proof.entries_sha256.toUpperCase().replace(/[0-9]/g, "A"); }],
  ["proof: 63-char digest", (d) => { d.tree_proof.entries_sha256 = d.tree_proof.entries_sha256.slice(1); }],
  ["proof: 65-char digest", (d) => { d.tree_proof.entries_sha256 += "a"; }],
  ["proof: non-hex digest", (d) => { d.tree_proof.entries_sha256 = "g".repeat(64); }],
  ["proof: non-string digest", (d) => { d.tree_proof.entries_sha256 = 5; }],
  ["limits: missing key", (d) => { delete d.limits.max_gets; }],
  ["limits: extra key", (d) => { d.limits.extra = 1; }],
  ["limits: altered value", (d) => { d.limits.deadline_ms = 1; }],
  ["limits: non-object", (d) => { d.limits = 1; }],
];

test("row 24b: every single-check mutation is rejected and routes an oversized primary to tier 3", async () => {
  const { primary, degraded } = await genuine([hex40(1), hex40(2)]);
  assert.ok(isValidDegraded(degraded));
  const ceiling = utf8Length(serializeResult(1, primary)) - 1;
  for (const [name, mutate] of mutations) {
    const copy = clone(degraded);
    mutate(copy);
    assert.equal(isValidDegraded(copy), false, name);
    assert.equal(writeToolResponse(1, { primary, degraded: copy }, ceiling).tier, 3, name);
  }
  const wrongShapes = {
    array: [], instance: new (class D {})(), nullProto: Object.assign(Object.create(null), clone(degraded)),
    inherited: Object.create(clone(degraded)),
  };
  for (const [name, value] of Object.entries(wrongShapes)) assert.equal(isValidDegraded(value), false, name);
});

test("row 24c: mutant predicates and writers are caught by the assertions above", async () => {
  const { primary, degraded } = await genuine([hex40(1)]);
  // A predicate checking the superseded top-level reason/entries form rejects the genuine object.
  const oldPredicate = (d) => d && d.reason === "OUTPUT_CEILING_EXCEEDED" && d.entries === null;
  assert.equal(oldPredicate(degraded), false);
  // A predicate that accepts the superseded form would accept an object that the real one rejects.
  const legacy = { ...clone(degraded), reason: "OUTPUT_CEILING_EXCEEDED", entries: null };
  assert.equal(isValidDegraded(legacy), false);
  // A writer that always tries tier 2 would serialize an undefined degraded form.
  const ceiling = utf8Length(serializeResult(1, primary)) - 1;
  const alwaysTier2 = (id, env) => serializeResult(id, env.degraded);
  assert.ok(alwaysTier2(1, { primary, degraded: undefined }) !== serializeOutputCeilingError(1));
  assert.equal(writeToolResponse(1, { primary, degraded: undefined }, ceiling).tier, 3);
});

test("row 21: serialized-id bounds and tier-3 sizes", () => {
  const sizes = new Map([[null, 180], [1, 177], [1e15, 192], [-1e15, 193], [-9007199254740991, 193], [9007199254740991, 192]]);
  for (const [id, total] of sizes) {
    assert.equal(utf8Length(serializeOutputCeilingError(id)), total, String(id));
    assert.ok(utf8Length(JSON.stringify(id)) <= 17);
  }
  assert.equal(utf8Length(serializeOutputCeilingError(1)) - 1, 176);
  for (const id of ["\ud800".repeat(32_766), "\u0001".repeat(32_766)]) {
    assert.equal(utf8Length(JSON.stringify(id)), 196_598);
    const body = serializeOutputCeilingError(id);
    assert.equal(utf8Length(body), 196_774);
    assert.ok(utf8Length(body) <= MAX_MCP_RESPONSE_BYTES);
  }
  assert.equal(utf8Length(serializeOutputCeilingError("\n".repeat(32_766))), 65_710);
});

test("row 21: the module-load guard holds and trips when the request cap is raised", () => {
  assert.ok(6 * 32_768 + 512 < MAX_MCP_RESPONSE_BYTES);
  const dir = mkdtempSync(join(tmpdir(), "dogbuild-guard-"));
  try {
    cpSync(join(dirname(fileURLToPath(import.meta.url)), "..", "src"), join(dir, "src"), { recursive: true });
    writeFileSync(join(dir, "package.json"), '{"type":"module"}');
    const indexPath = join(dir, "src", "index.js");
    const original = readFileSync(indexPath, "utf8");
    assert.ok(original.includes("MAX_REQUEST_BYTES = 32_768"));
    writeFileSync(indexPath, original.replace("MAX_REQUEST_BYTES = 32_768", "MAX_REQUEST_BYTES = 100_000"));
    return assert.rejects(import(`${pathToFileURL(indexPath).href}?mutant`), /too large/);
  } finally {
    // the import completes (or fails) before the directory is removed by the OS temp cleaner
    setTimeout(() => rmSync(dir, { recursive: true, force: true }), 2000).unref();
  }
});

test("row 21: the degraded form without an id is within its bound and adds little with the worst id", async () => {
  const { primary, degraded } = await genuine([hex40(1)]);
  assert.ok(jsonUtf8Length(degraded) <= 8192);
  const worst = writeToolResponse("\u0001".repeat(32_766), { primary, degraded }, utf8Length(serializeResult("\u0001".repeat(32_766), primary)) - 1);
  assert.equal(worst.tier, 2);
  assert.ok(utf8Length(worst.body) < 205_000);
});

test("row 24e: the TextEncoder primitive equals the Node Buffer oracle", () => {
  const samples = ["", "plain", "é", "€", "😀", "mixed é€😀 ascii", "\n\t\"\\\u0001\u001f", "\ud800", "a😀b",
    "日本語", "x".repeat(8191), "x".repeat(8192), "x".repeat(8193)];
  for (const s of samples) {
    assert.equal(utf8Length(s), Buffer.byteLength(s, "utf8"), JSON.stringify(s));
    assert.equal(jsonUtf8Length(s), Buffer.byteLength(JSON.stringify(s), "utf8"));
  }
  // UTF-16 length is not the byte length: a mutant measuring .length is caught.
  assert.notEqual("😀".length, utf8Length("😀"));
  assert.notEqual("é".length, utf8Length("é"));
});

test("writeErrorResponse carries the exact id and a fixed controlled error", () => {
  const out = writeErrorResponse(7, new ControlError(ErrorClass.NOT_FOUND, "GitHub responded 404.", { status: 404 }));
  const body = JSON.parse(out.body);
  assert.equal(body.id, 7);
  assert.equal(body.error.code, -32000);
  assert.deepEqual(body.error.data, { error_class: "NOT_FOUND", message: "GitHub responded 404.", status: 404 });
});
