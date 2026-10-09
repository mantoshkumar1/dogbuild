import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { generateGitFixture, gitAvailable } from "./raw-support.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const NEW_MODULES = ["raw-commit.js", "tree-proof.js", "proof-encoding.js", "output.js"];

test("row 24f: new production modules never reference Buffer, node:buffer or require", () => {
  for (const file of [...NEW_MODULES, "index.js", "github.js", "handlers.js", "tools.js"]) {
    const source = readFileSync(join(root, "src", file), "utf8");
    assert.ok(!/\bBuffer\b/.test(source), `${file} references Buffer`);
    assert.ok(!/node:buffer/.test(source), `${file} imports node:buffer`);
    assert.ok(!/\brequire\s*\(/.test(source), `${file} uses require`);
  }
});

test("row 24d: with Buffer deleted before a fresh import the Worker still serves, ceilings and ids intact", () => {
  const script = `
    // Harness stubs: Node's bundled undici needs Buffer internally, the Workers runtime does not. The Worker
    // only needs request.{method,url,headers,text()} and a Response constructor, so supply minimal stand-ins.
    const headers = (h) => new Headers(h);
    const warm = headers({ a: "b" });
    globalThis.Response = class { constructor(body, init = {}) { this.bodyText = body === null || body === undefined ? "" : String(body); this.status = init.status ?? 200; this.headers = headers(init.headers); } async text() { return this.bodyText; } static json(v, init = {}) { return new this(JSON.stringify(v), { ...init, headers: { "content-type": "application/json", ...(init.headers || {}) } }); } };
    delete globalThis.Buffer;
    if (typeof globalThis.Buffer !== "undefined") throw new Error("Buffer still defined");
    const mod = await import(${JSON.stringify(join(root, "src/index.js"))});
    for (const m of ${JSON.stringify(NEW_MODULES)}) await import(${JSON.stringify(join(root, "src") + "/")} + m);
    const env = { GITHUB_TOKEN: "t", ALLOWED_REPOS: "o/r", MCP_PATH_SECRET: "test-path-secret-0123456789abcdef", MCP_ACCESS_TOKEN: "TEST_MCP_ACCESS_TOKEN_NOT_REAL_0123456789abcdef" };
    let fetched = 0;
    globalThis.fetch = async () => { fetched += 1; throw new Error("no network"); };
    const post = (body) => mod.default.fetch({ method: "POST", url: "https://x/mcp/" + env.MCP_PATH_SECRET, headers: headers({ Authorization: "Bearer " + env.MCP_ACCESS_TOKEN }), text: async () => body, body: {} }, env);
    const call = (id, args) => post('{"jsonrpc":"2.0",' + id + '"method":"tools/call","params":{"name":"get_raw_commit","arguments":' + JSON.stringify(args) + '}}');
    const out = [];
    const a = await call('', { owner: "o", repo: "r", sha: "c".repeat(40) });
    out.push([a.status, await a.text()]);
    const b = await call('"id":true,', { owner: "o", repo: "r", sha: "c".repeat(40) });
    out.push([b.status, await b.text()]);
    const c = await call('"id":7,', { owner: "o", repo: "r", sha: "C" });
    out.push([c.status, await c.text()]);
    const d = await call('"id":8,', { owner: "x", repo: "y", sha: "c".repeat(40) });
    out.push([d.status, await d.text()]);
    console.log(JSON.stringify({ out, fetched, buffer: typeof globalThis.Buffer }));
  `;
  const run = spawnSync(process.execPath, ["--input-type=module", "-e", script], { encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr);
  const result = JSON.parse(run.stdout.trim().split("\n").pop());
  assert.equal(result.buffer, "undefined");
  assert.equal(result.fetched, 0);
  assert.deepEqual(result.out[0], [202, ""]);
  assert.equal(result.out[1][0], 400);
  assert.equal(JSON.parse(result.out[1][1]).error.data.reason, "INVALID_REQUEST_ID");
  assert.equal(JSON.parse(result.out[2][1]).id, 7);
  assert.equal(JSON.parse(result.out[2][1]).error.data.reason, "INVALID_SHA");
  assert.equal(JSON.parse(result.out[3][1]).error.data.error_class, "ALLOWLIST_DENIED");
});

// ---------------------------------------------------------------------------------------------------------------------
// R371 / F-370-1: accepted row 24d/24f proof. Everything below is additive; the two tests above are unchanged.
//
// An isolated child process (1) reads genuine accepted A/B git fixtures and prepares every request/response byte,
// (2) runs `delete globalThis.Buffer` and asserts it is undefined, and (3) only then cache-fresh imports the real
// src/index.js and every production module, and drives the real default-export transport, the real three-GET raw-commit
// path and the real four-tier writer.
//
// Node-infrastructure note (the only harness accommodation): Node's bundled undici constructs any Response/Request
// that has a body through `Buffer.byteLength`/`Buffer.from`, whereas the Workers runtime does not. After the delete and
// the "undefined" assertion, the child therefore installs a global `Buffer` accessor that yields the real Buffer ONLY to a
// caller whose stack frame is inside `node:` internals (the platform), and `undefined` to everything else, including the
// test code and every production file. Production `Buffer` use, at import time or at run time, still raises, which the
// mutation tests below prove. No Response, Request, fetch or production function is replaced by a stand-in.
// ---------------------------------------------------------------------------------------------------------------------
const CAP = 2_097_152;
const MARKER_DELETE = "delete globalThis.Buffer;";
const MARKER_ASSERT = 'if (typeof globalThis.Buffer !== "undefined") throw new Error("Buffer still defined");';
const CHILD_SOURCE = String.raw`
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { join } from "node:path";

const ROOT = process.env.DOGBUILD_ROOT;
const data = JSON.parse(readFileSync(process.env.DOGBUILD_DATA, "utf8"));
const support = await import(pathToFileURL(process.env.DOGBUILD_SUPPORT).href);
const { ENV, GIT, OWNER, REPO, callRaw, commitBody, treeBody } = support;
const enc = new TextEncoder();
const CAP = 2097152;
const CHUNK = 65536;
const bytes = (obj) => enc.encode(JSON.stringify(obj, null, 2));

// 1. Prepare every genuine fixture response body BEFORE Buffer is deleted (plain Uint8Arrays).
const prepared = {};
for (const key of ["A", "B"]) {
  const fx = data[key];
  const top = fx.entries.filter((e) => !e.path.includes("/"));
  prepared[key] = { fx, commit: bytes(commitBody(fx.commit, fx.tree, fx.parents)), root: bytes(treeBody(fx.tree, top)), rec: bytes(treeBody(fx.tree, fx.entries)) };
}
const paddedRec = new Uint8Array(CAP + 1).fill(32);
paddedRec.set(prepared.B.rec, 0);

// 2. Delete Buffer, then prove it is absent.
const order = [];
const RealBuffer = globalThis.Buffer;
order.push("delete");
delete globalThis.Buffer;
if (typeof globalThis.Buffer !== "undefined") throw new Error("Buffer still defined");
order.push("asserted-undefined");
Object.defineProperty(globalThis, "Buffer", {
  configurable: true,
  get() {
    const caller = (new Error().stack || "").split("\n")[2] || "";
    return caller.includes("node:") ? RealBuffer : undefined;
  },
});
if (typeof globalThis.Buffer !== "undefined" || typeof Buffer !== "undefined") throw new Error("Buffer visible to test code");
order.push("shim-undefined-to-user-code");

// 3. Only now: cache-fresh imports of the real entrypoint and every production module.
const nonce = String(Date.now()) + "-" + String(Math.random()).slice(2);
const loaded = [];
const fresh = async (file) => {
  const m = await import(pathToFileURL(join(ROOT, "src", file)).href + "?fresh=" + nonce);
  loaded.push(file);
  return m;
};
const index = await fresh("index.js");
const modules = {};
for (const file of ["raw-commit.js", "tree-proof.js", "proof-encoding.js", "output.js", "github.js", "handlers.js", "tools.js", "errors.js", "allowlist.js"]) modules[file] = await fresh(file);
order.push("imported");

// 4. Real transport + real three-GET path, genuine responses delivered as 64 KiB chunked streams.
let gets = [];
const streamOf = (body) => {
  let offset = 0;
  return new ReadableStream({
    pull(controller) {
      if (offset >= body.length) { controller.close(); return; }
      const end = Math.min(body.length, offset + CHUNK);
      controller.enqueue(body.subarray(offset, end));
      offset = end;
    },
  });
};
const install = (key, recBody) => {
  const p = prepared[key];
  const routes = {
    [GIT + "/commits/" + p.fx.commit]: p.commit,
    [GIT + "/trees/" + p.fx.tree]: p.root,
    [GIT + "/trees/" + p.fx.tree + "?recursive=1"]: recBody || p.rec,
  };
  gets = [];
  globalThis.fetch = async (url, init = {}) => {
    const u = new URL(String(url));
    gets.push((init.method || "GET") + " " + u.pathname + u.search);
    const body = routes[u.pathname + u.search];
    if (!body) throw new Error("unmatched request " + u.pathname + u.search);
    return new Response(streamOf(body), { status: 200, headers: { "content-type": "application/json; charset=utf-8" } });
  };
};
const { utf8Length, jsonUtf8Length, writeToolResponse, DEGRADED_MAX_BYTES, TIER4_BODY } = modules["output.js"];
const args = (key) => ({ owner: OWNER, repo: REPO, sha: prepared[key].fx.commit });
const transport = async (key, id, recBody) => {
  install(key, recBody);
  const response = await callRaw(index.default, args(key), { id });
  const text = await response.text();
  const parsed = JSON.parse(text);
  const value = parsed.result ? JSON.parse(parsed.result.content[0].text) : null;
  return {
    status: response.status, contentType: response.headers.get("content-type"), id: parsed.id, bodyBytes: utf8Length(text),
    resultText: parsed.result ? parsed.result.content[0].text : null,
    resultBytes: parsed.result ? utf8Length(parsed.result.content[0].text) : null,
    value: value && { status: value.status, complete: value.complete, reason: value.incomplete_reason, entries: value.tree_proof ? value.tree_proof.entries : "none", sha: value.sha, parents: value.parents ? value.parents.length : null, entriesSha256: value.tree_proof ? value.tree_proof.entries_sha256 : null },
    error: parsed.error ? { code: parsed.error.code, message: parsed.error.message, reason: parsed.error.data && parsed.error.data.reason, errorClass: parsed.error.data && parsed.error.data.error_class } : null,
    hasResult: parsed.result !== undefined,
    gets,
  };
};
const production = async (key, recBody) => {
  install(key, recBody);
  const result = await modules["raw-commit.js"].getRawCommit(ENV, args(key));
  return { result, gets };
};

const attempt = async (fn) => { try { return await fn(); } catch (e) { return { crashed: String(e && e.message) }; } };

const report = { order, bufferType: typeof globalThis.Buffer, loaded, degradedMax: DEGRADED_MAX_BYTES, tier4Body: TIER4_BODY };

report.A = await attempt(() => transport("A", "abc"));
report.B = await attempt(() => transport("B", "abc"));
report.Bnum = await attempt(() => transport("B", 7));

const pa = await production("A");
const pb = await production("B");
report.primaryA = { status: pa.result.primary.status, complete: pa.result.primary.complete, tree: pa.result.primary.tree_sha, commit: pa.result.primary.sha, parents: pa.result.primary.parents.length, gets: pa.gets, primaryBytes: jsonUtf8Length(pa.result.primary), degradedBytes: jsonUtf8Length(pa.result.degraded) };
report.primaryB = { status: pb.result.primary.status, complete: pb.result.primary.complete, tree: pb.result.primary.tree_sha, commit: pb.result.primary.sha, parents: pb.result.primary.parents.length, gets: pb.gets, primaryBytes: jsonUtf8Length(pb.result.primary), degradedBytes: jsonUtf8Length(pb.result.degraded) };

report.incomplete = await attempt(async () => {
// Non-COMPLETE primary (genuine RESPONSE_TOO_LARGE from the 2,097,153-byte padded recursive body), no degraded form.
const over = await production("B", paddedRec);
const overText = JSON.stringify({ jsonrpc: "2.0", id: "abc", result: { content: [{ type: "text", text: JSON.stringify(over.result.primary) }] } });
const overLen = utf8Length(overText);
const tight = writeToolResponse("abc", over.result, overLen - 1);
const loose = writeToolResponse("abc", over.result);
const incomplete = {
  status: over.result.primary.status, reason: over.result.primary.incomplete_reason, degraded: over.result.degraded, gets: over.gets,
  looseTier: loose.tier, looseId: JSON.parse(loose.body).id, tightTier: tight.tier, tightStatus: tight.status, tightId: JSON.parse(tight.body).id,
  tightReason: JSON.parse(tight.body).error.data.reason, tightBytes: utf8Length(tight.body), tightHasResult: JSON.parse(tight.body).result !== undefined,
};
const incompleteViaTransport = await transport("B", "abc", paddedRec);
incomplete.transport = { tier1Status: incompleteViaTransport.value && incompleteViaTransport.value.status, reason: incompleteViaTransport.value && incompleteViaTransport.value.reason, id: incompleteViaTransport.id, gets: incompleteViaTransport.gets };

return incomplete;
});
report.tier4 = await attempt(async () => {
// Tier 4: injected tiny ceiling on the real writer with the real A envelope; then through a real Response.
const t4 = writeToolResponse("abc", pa.result, 50);
const t4response = new Response(t4.body, { status: t4.status, headers: { "content-type": t4.contentType } });
return { tier: t4.tier, status: t4.status, contentType: t4.contentType, body: t4.body, responseStatus: t4response.status, responseContentType: t4response.headers.get("content-type"), responseText: await t4response.text() };
});
const extra = await attempt(async () => {
const t4b = writeToolResponse("abc", pb.result, 50);
const tier4B = { tier: t4b.tier, status: t4b.status, body: t4b.body };
// Writer tiers for the real A/B envelopes at the default ceiling.
const wa = writeToolResponse("abc", pa.result);
const wb = writeToolResponse("abc", pb.result);
const writer = { aTier: wa.tier, aBytes: wa.body ? JSON.parse(wa.body).result.content[0].text.length : null, bTier: wb.tier, bId: JSON.parse(wb.body).id };
return { tier4B, writer };
});
report.tier4B = extra.tier4B;
report.writer = extra.writer;
report.extraCrash = extra.crashed;
console.log(JSON.stringify(report));
`;

/** Source-order guard (row 24f): no production reference before delete+assert; every production import after them. */
export function orderViolations(source) {
  const problems = [];
  const del = source.indexOf(MARKER_DELETE);
  const assertAt = source.indexOf(MARKER_ASSERT);
  if (del < 0) problems.push("missing delete statement");
  if (assertAt < 0) problems.push("missing absent assertion");
  if (del >= 0 && assertAt >= 0 && !(del < assertAt)) problems.push("assert precedes delete");
  const gate = assertAt;
  const productionRefs = [...source.matchAll(/\bfresh\(|\bjoin\(ROOT|["']src["']|\.\.?\/src\//g)].map((m) => ({ at: m.index, text: m[0] }));
  if (productionRefs.filter((r) => r.text === "fresh(").length < 2) problems.push("too few fresh production imports");
  for (const ref of productionRefs) {
    if (gate < 0 || ref.at < gate) problems.push(`production reference ${JSON.stringify(ref.text)} before the absent assertion`);
  }
  if (/^\s*import\s[^;]*from\s+["'][^"']*src\//m.test(source)) problems.push("static import of production source");
  return problems;
}

const A_PIN = { commit: "97489121fe43af26b4b527785b326fc87b427471", tree: "32ad195e7dc34e81c76b32ced5320b039c07ae8c", sha256: "313a61297b24d750be89ef6d4db48d75636bc2c644711f31d68e395fd812eeaf" };
const B_PIN = { commit: "906d7ab036de24048075cf177450f1271d0e19ca", tree: "91872b1ea16d1ae7d2c87aed60dd32b3deeb0c0b", sha256: "2159d1c925d2d0b8331c3a40f7d395e91bfedbb8e7709340f2623ffa34edd98b" };
const supportPath = join(root, "test", "raw-support.mjs");
let dataFile = null;
let scratch = null;

function fixtureData() {
  if (dataFile) return dataFile;
  scratch = mkdtempSync(join(tmpdir(), "dogbuild-nobuffer-"));
  dataFile = join(scratch, "fixtures.json");
  const make = (L1, L2) => {
    const fx = generateGitFixture({ L1, L2, parents: 170 });
    return { commit: fx.commit, tree: fx.tree, parents: fx.parents, entries: fx.entries };
  };
  writeFileSync(dataFile, JSON.stringify({ A: make(100, 100), B: make(122, 127) }));
  return dataFile;
}

function runChild(srcRoot, source = CHILD_SOURCE) {
  const run = spawnSync(process.execPath, ["--input-type=module", "-e", source], {
    encoding: "utf8", maxBuffer: 1 << 26,
    env: { ...process.env, DOGBUILD_ROOT: srcRoot, DOGBUILD_DATA: fixtureData(), DOGBUILD_SUPPORT: supportPath },
  });
  let report = null;
  try { report = JSON.parse(run.stdout.trim().split("\n").pop()); } catch { /* crash: no report */ }
  return { status: run.status, stderr: run.stderr, report };
}

/** Every acceptance assertion as a list of problems; an empty list means the child proved the accepted behavior. */
function evaluate(run) {
  const problems = [];
  const check = (ok, what) => { if (!ok) problems.push(what); };
  const sec = (name, fn) => { try { fn(); } catch (e) { problems.push(`${name} not evaluable: ${e.message}`); } };
  if (run.status !== 0 || !run.report) {
    return [`child failed (status ${run.status}): ${String(run.stderr).split("\n").find((l) => /Error/.test(l)) || "no report"}`];
  }
  const r = run.report;
  check(JSON.stringify(r.order) === JSON.stringify(["delete", "asserted-undefined", "shim-undefined-to-user-code", "imported"]), "order delete -> assert -> shim -> import");
  check(r.bufferType === "undefined", "Buffer undefined in the child");
  check(["index.js", "raw-commit.js", "tree-proof.js", "proof-encoding.js", "output.js"].every((f) => r.loaded.includes(f)), "all new modules freshly imported");
  check(r.degradedMax === 8192, "DEGRADED_MAX_BYTES 8192");
  check(r.tier4Body === "Output ceiling exceeded", "TIER4_BODY text");
  // genuine fixtures, three GETs, verified COMPLETE primaries
  for (const [name, pin, key] of [["A", A_PIN, "primaryA"], ["B", B_PIN, "primaryB"]]) sec(`fixture ${name}`, () => {
    const p = r[key];
    check(p.commit === pin.commit && p.tree === pin.tree, `fixture ${name} identity`);
    check(p.status === "COMPLETE" && p.complete === true && p.parents === 170, `fixture ${name} verified COMPLETE primary`);
    check(p.primaryBytes > 524_288, `fixture ${name} primary exceeds the ceiling`);
    check(p.gets.length === 3 && p.gets[0].includes("/git/commits/") && p.gets[1].endsWith(`/git/trees/${pin.tree}`) && p.gets[2].endsWith(`${pin.tree}?recursive=1`), `fixture ${name} exactly three GETs`);
  });
  check(r.primaryA.degradedBytes === 8192, "A degraded form measures 8,192");
  check(r.primaryB.degradedBytes === 8193, "B degraded form measures 8,193");
  for (const k of ["A", "B", "Bnum", "incomplete", "tier4"]) check(!(r[k] && r[k].crashed), `${k} scenario crashed: ${r[k] && r[k].crashed}`);
  check(!r.extraCrash, `tier4B/writer scenario crashed: ${r.extraCrash}`);
  sec("A", () => {
  // A -> tier 2 through the real transport
  const A = r.A;
  check(A.status === 200 && A.contentType === "application/json" && A.id === "abc" && A.hasResult && A.error === null, "A transport tier-2 envelope with id abc");
  check(A.resultBytes === 8192 && A.value && A.value.status === "INCOMPLETE" && A.value.reason === "OUTPUT_CEILING_EXCEEDED" && A.value.complete === false && A.value.entries === null, "A tier 2 degraded result of 8,192 bytes");
  check(A.value && A.value.parents === 170 && A.value.entriesSha256 === A_PIN.sha256 && A.value.sha === A_PIN.commit, "A degraded result carries the verified proof");
  check(A.gets.length === 3 && A.bodyBytes <= 524_288, "A three GETs and within the MCP ceiling");
  });
  sec("B", () => {
  // B -> tier 3 same-ID fixed error
  const B = r.B;
  check(B.status === 200 && B.id === "abc" && B.hasResult === false && B.value === null, "B transport tier-3 has no result");
  check(B.error && B.error.code === -32000 && B.error.reason === "OUTPUT_CEILING_EXCEEDED" && B.error.errorClass === "UPSTREAM_ERROR" && B.error.message === "MCP response exceeded the output ceiling.", "B fixed same-ID tier-3 error");
  check(B.gets.length === 3, "B three GETs");
  check(r.Bnum.id === 7 && r.Bnum.error && r.Bnum.error.reason === "OUTPUT_CEILING_EXCEEDED", "B tier 3 keeps a numeric id");
  });
  sec("non-COMPLETE", () => {
  // non-COMPLETE / no degraded -> tier 3
  const n = r.incomplete;
  check(n.status === "INCOMPLETE" && n.reason === "RESPONSE_TOO_LARGE" && n.degraded === null && n.gets.length === 3, "non-COMPLETE primary with no degraded form from three real GETs");
  check(n.looseTier === 1 && n.looseId === "abc", "non-COMPLETE primary is tier 1 when it fits");
  check(n.tightTier === 3 && n.tightStatus === 200 && n.tightId === "abc" && n.tightReason === "OUTPUT_CEILING_EXCEEDED" && n.tightHasResult === false, "non-COMPLETE/no-degraded takes tier 3 with the same id");
  check(n.transport.tier1Status === "INCOMPLETE" && n.transport.reason === "RESPONSE_TOO_LARGE" && n.transport.id === "abc" && n.transport.gets.length === 3, "non-COMPLETE through the real transport");
  });
  sec("tier 4", () => {
  // tier 4
  const t = r.tier4;
  check(t.tier === 4 && t.status === 500 && t.contentType === "text/plain" && t.body === "Output ceiling exceeded", "tiny ceiling: tier 4, 500, exact plain text");
  check(t.responseStatus === 500 && t.responseContentType === "text/plain" && t.responseText === "Output ceiling exceeded", "tier 4 through a real Response");
  check(r.tier4B.tier === 4 && r.tier4B.status === 500 && r.tier4B.body === "Output ceiling exceeded", "tiny ceiling for B: tier 4");
  check(r.writer.aTier === 2 && r.writer.bTier === 3 && r.writer.bId === "abc", "real writer tiers for the real envelopes");
  });
  return problems;
}

let baselineRun = null;
const baseline = () => (baselineRun ??= runChild(root));

function mutantRoot(label, edits) {
  const dir = mkdtempSync(join(tmpdir(), `dogbuild-mutant-${label}-`));
  cpSync(join(root, "src"), join(dir, "src"), { recursive: true });
  for (const [file, from, to] of edits) {
    const target = join(dir, "src", file);
    const text = readFileSync(target, "utf8");
    assert.ok(text.includes(from), `mutation anchor missing in ${file}: ${from}`);
    writeFileSync(target, text.split(from).join(to));
  }
  return dir;
}

test("row 24d/24f: fixtures A and B are genuine git objects (pinned) and git is available", { timeout: 180_000 }, () => {
  assert.equal(gitAvailable(), true);
  const data = JSON.parse(readFileSync(fixtureData(), "utf8"));
  assert.equal(data.A.commit, A_PIN.commit);
  assert.equal(data.A.tree, A_PIN.tree);
  assert.equal(data.B.commit, B_PIN.commit);
  assert.equal(data.B.tree, B_PIN.tree);
  assert.equal(data.A.parents.length, 170);
  assert.equal(data.B.entries.length, 4000);
});

test("row 24f: static source order - the child deletes and asserts Buffer before any production import", () => {
  assert.deepEqual(orderViolations(CHILD_SOURCE), []);
  const del = CHILD_SOURCE.indexOf(MARKER_DELETE);
  const absent = CHILD_SOURCE.indexOf(MARKER_ASSERT);
  const firstImport = CHILD_SOURCE.indexOf("fresh(");
  const entry = CHILD_SOURCE.indexOf('fresh("index.js")');
  assert.ok(del > 0 && del < absent && absent < firstImport && firstImport <= entry);
  // the production modules are imported dynamically, never statically, and the whole thing is in this very file
  assert.ok(!/^import .*src\//m.test(CHILD_SOURCE));
  assert.ok(readFileSync(fileURLToPath(import.meta.url), "utf8").includes(CHILD_SOURCE.slice(0, 200)));
  // negative controls for the guard itself: an import-first refactor and a missing assertion are both detected
  const importFirst = CHILD_SOURCE.replace(MARKER_DELETE, "").replace(MARKER_ASSERT, "").replace("const prepared = {};", `const early = await import(pathToFileURL(join(ROOT, "src", "output.js")).href);\n${MARKER_DELETE}\n${MARKER_ASSERT}\nconst prepared = {};`);
  assert.notDeepEqual(orderViolations(importFirst), []);
  assert.notDeepEqual(orderViolations(CHILD_SOURCE.replace(MARKER_ASSERT, "")), []);
  assert.notDeepEqual(orderViolations(CHILD_SOURCE.replace(MARKER_DELETE, "")), []);
  assert.notDeepEqual(orderViolations(`import { x } from "../src/output.js";\n${CHILD_SOURCE}`), []);
});

test("row 24d: after delete-then-fresh-import the real transport serves genuine A (tier 2), B (tier 3), non-COMPLETE (tier 3) and tiny-ceiling (tier 4) over three real GETs", { timeout: 300_000 }, () => {
  const run = baseline();
  assert.deepEqual(evaluate(run), [], run.stderr);
  assert.equal(run.report.A.resultBytes, 8192);
  assert.equal(run.report.primaryB.degradedBytes, 8193);
});

test("row 24c: import-time Buffer use passes the old import-then-delete order but fails delete-then-import", { timeout: 300_000 }, () => {
  const mutated = mutantRoot("import-time", [["output.js", 'const UTF8 = new TextEncoder();', 'const UTF8 = new TextEncoder();\nexport const __bufferProbe = Buffer.byteLength("x");']]);
  try {
    // old order (R351): import first, delete afterwards - the defect is invisible
    const oldOrder = spawnSync(process.execPath, ["--input-type=module", "-e",
      `import { pathToFileURL } from "node:url"; import { join } from "node:path";
       await import(pathToFileURL(join(process.env.DOGBUILD_ROOT, "src", "output.js")).href);
       delete globalThis.Buffer; console.log("old-order-passes");`],
    { encoding: "utf8", env: { ...process.env, DOGBUILD_ROOT: mutated } });
    assert.equal(oldOrder.status, 0);
    assert.match(oldOrder.stdout, /old-order-passes/);
    // accepted order: delete first
    const run = runChild(mutated);
    const problems = evaluate(run);
    assert.notDeepEqual(problems, []);
    assert.match(problems[0], /child failed/);
    assert.match(run.stderr, /Buffer|undefined/);
  } finally { rmSync(mutated, { recursive: true, force: true }); }
});

const MUTATIONS = [
  ["runtime-buffer", "runtime Buffer use in the writer", [["output.js", "export const utf8Length = (text) => UTF8.encode(text).length;", "export const utf8Length = (text) => Buffer.byteLength(text);"]], /scenario crashed|child failed/],
  ["runtime-buffer-serializer", "runtime Buffer use on the success path", [["output.js", "export function serializeResult(id, value) {", "export function serializeResult(id, value) {\n  Buffer.from(\"x\");"]], /reading .from.|A transport tier-2/],
  ["import-time-index", "import-time Buffer use in the entrypoint", [["index.js", "export const SERVER_NAME", "export const __b = Buffer.byteLength(\"x\");\nexport const SERVER_NAME"]], /child failed/],
  ["import-time-tree-proof", "import-time Buffer use in tree-proof", [["tree-proof.js", "\n", "\nglobalThis.Buffer.from(\"x\");\n"]], /child failed/],
  ["gate-8193", "gate raised to 8,193 (B would take tier 2)", [["output.js", "export const DEGRADED_MAX_BYTES = 8192;", "export const DEGRADED_MAX_BYTES = 8193;"]], /B transport tier-3|B fixed|B scenario|real writer/],
  ["gate-8191", "gate lowered to 8,191 (A would take tier 3)", [["output.js", "export const DEGRADED_MAX_BYTES = 8192;", "export const DEGRADED_MAX_BYTES = 8191;"]], /A (transport|tier|scenario)|real writer/],
  ["no-tier-2", "tier 2 removed", [["output.js", "if (isValidDegraded(envelope.degraded)) {", "if (false) {"]], /A (transport|tier|scenario)|real writer/],
  ["tier-2-always", "invalid/absent degraded form falls through to tier 2", [["output.js", "if (isValidDegraded(envelope.degraded)) {", "if (true) {"]], /B (transport|fixed|scenario)|non-COMPLETE|incomplete scenario|real writer/],
  ["tier-3-no-id", "tier 3 loses the exact id", [["output.js", "return JSON.stringify({\n    jsonrpc: \"2.0\",\n    id,\n    error: {\n      code: -32000,\n      message: \"MCP response exceeded", "return JSON.stringify({\n    jsonrpc: \"2.0\",\n    id: null,\n    error: {\n      code: -32000,\n      message: \"MCP response exceeded"]], /B (transport|fixed|scenario)|numeric id|non-COMPLETE|incomplete scenario/],
  ["no-tier-3", "tier 3 removed (straight to tier 4)", [["output.js", "if (utf8Length(t3) <= ceilingBytes) return { tier: 3, status: 200, contentType: \"application/json\", body: t3 };\n  return { tier: 4, status: 500, contentType: \"text/plain\", body: TIER4_BODY };\n}\n\n/** JSON-RPC error", "return { tier: 4, status: 500, contentType: \"text/plain\", body: TIER4_BODY };\n}\n\n/** JSON-RPC error"]], /B (transport|fixed|scenario)|non-COMPLETE|incomplete scenario/],
  ["tier-4-status", "tier 4 returns 200 instead of 500", [["output.js", "status: 500, contentType: \"text/plain\"", "status: 200, contentType: \"text/plain\""]], /tier 4|tiny ceiling/],
  ["tier-4-body", "tier 4 plain text changed", [["output.js", "export const TIER4_BODY = \"Output ceiling exceeded\";", "export const TIER4_BODY = \"Output ceiling exceeded.\";"]], /TIER4_BODY|tier 4|tiny ceiling/],
];

for (const [label, title, edits, expected] of MUTATIONS) {
  test(`row 24c mutation ${label}: ${title} fails the Buffer-free success-path proof`, { timeout: 300_000 }, () => {
    const mutated = mutantRoot(label, edits);
    try {
      const run = runChild(mutated);
      const problems = evaluate(run);
      assert.notDeepEqual(problems, [], `mutation ${label} was not detected`);
      assert.ok(problems.some((p) => expected.test(p)), `unexpected detection for ${label}: ${problems.join(" | ")}`);
    } finally { rmSync(mutated, { recursive: true, force: true }); }
  });
}

test("row 24c: restoring the unmodified source passes the full Buffer-free proof again", { timeout: 300_000 }, () => {
  const restored = mutantRoot("restored", []);
  try {
    const run = runChild(restored);
    assert.deepEqual(evaluate(run), [], run.stderr);
  } finally {
    rmSync(restored, { recursive: true, force: true });
    if (scratch) rmSync(scratch, { recursive: true, force: true });
  }
});
