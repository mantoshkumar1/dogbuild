import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { GIT, generateGitFixture, gitAvailable } from "./raw-support.mjs";

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
// R373 / F-372-1: true-realm replacement of the R371 harness. Everything below is additive; the two tests above are unchanged.
//
// R371 hid `Buffer` from ordinary code with a global accessor that inspected the call stack. Codex R372 proved that is not
// an absence boundary: a user function whose stack mentions `node:` receives the real Buffer and the accessor recreates an
// own global property. That accessor is gone. Production now runs in a genuine isolated realm:
//
//   host realm (the child process)           production realm (node:vm context, SourceTextModule)
//   --------------------------------         ------------------------------------------------------
//   real Node/undici Request, Response,      its own intrinsics only; `Buffer` never existed there and is deleted again
//   ReadableStream, URL, TextEncoder,        and asserted absent (typeof, own property, `in`) before the first production
//   TextDecoder, crypto.subtle, timers,      import; the context sandbox has a null prototype so `this.constructor` is the
//   AbortController, fixture routes          realm's own Object, not the host's
//
// The only things that connect them are a membrane of thin realm-native wrappers (REALM_BOOTSTRAP). Each wrapper delegates
// every operation to the genuine host object, crosses the boundary only as strings, numbers, plain JSON or COPIED bytes, and
// re-throws host errors as realm-native errors. Host objects (and with them `x.constructor.constructor`, which would reach the
// host global and the host Buffer) are never handed to production code. Production reaches a global `Response`, `Request`,
// `Headers`, `fetch`, `URL`, `TextEncoder`, `TextDecoder`, `crypto`, `AbortController` and timers, nothing else.
// ---------------------------------------------------------------------------------------------------------------------
const CAP = 2_097_152;
const MARKER_DELETE = "delete globalThis.Buffer;";
const MARKER_ASSERT = 'if (typeof globalThis.Buffer !== "undefined") throw new Error("Buffer still defined");';
const BRIDGED_GLOBALS = ["AbortController", "AbortSignal", "Headers", "Request", "Response", "TextDecoder", "TextEncoder", "URL", "clearTimeout", "crypto", "fetch", "setTimeout"];

/** Installed into the production realm by the host. Receives the host bridge once, in a closure no production code can reach. */
const REALM_BOOTSTRAP = String.raw`(function (bridge) {
"use strict";
const rewrap = (e) => {
  const name = e && typeof e.name === "string" ? e.name : "Error";
  const message = e && typeof e.message === "string" ? e.message : "";
  const C = name === "TypeError" ? TypeError : name === "RangeError" ? RangeError : Error;
  const err = new C(message);
  if (name === "AbortError" || name === "TimeoutError") Object.defineProperty(err, "name", { value: name, configurable: true });
  return err;
};
const call = (fn, ...args) => { try { return fn(...args); } catch (e) { throw rewrap(e); } };
const acall = async (fn, ...args) => { try { return await fn(...args); } catch (e) { throw rewrap(e); } };
const toNative = (hostBytes) => { const out = new Uint8Array(hostBytes.length); out.set(hostBytes); return out; };
const def = (name, value) => Object.defineProperty(globalThis, name, { value, writable: true, configurable: true, enumerable: false });

class Headers {
  #map = new Map();
  constructor(init) {
    if (init instanceof Headers) { init.forEach((v, k) => this.#map.set(k, v)); return; }
    if (Array.isArray(init)) { for (const [k, v] of init) this.#add(k, v); return; }
    if (init && typeof init === "object") for (const k of Object.keys(init)) this.#add(k, init[k]);
  }
  #add(k, v) {
    const key = String(k).toLowerCase();
    this.#map.set(key, this.#map.has(key) ? this.#map.get(key) + ", " + String(v) : String(v));
  }
  get(name) { const key = String(name).toLowerCase(); return this.#map.has(key) ? this.#map.get(key) : null; }
  has(name) { return this.#map.has(String(name).toLowerCase()); }
  forEach(fn) { for (const [k, v] of this.#map) fn(v, k, this); }
}
const headerObject = (h) => { const o = {}; if (h) new Headers(h).forEach((v, k) => { o[k] = v; }); return o; };
const headersJson = (h) => JSON.stringify(headerObject(h));

const hostResponses = new WeakMap();
const nativeReader = (hostReader) => ({
  async read() {
    const step = await acall(bridge.readerRead, hostReader);
    return step.done ? { done: true, value: undefined } : { done: false, value: toNative(step.value) };
  },
  cancel() { return acall(bridge.readerCancel, hostReader); },
  releaseLock() { call(bridge.readerRelease, hostReader); },
});
class Response {
  constructor(body, init) {
    const i = init || {};
    const host = call(bridge.newResponse, body === null || body === undefined ? null : String(body), i.status === undefined ? 200 : Number(i.status), headersJson(i.headers));
    hostResponses.set(this, host);
  }
  static json(value, init) {
    const i = init || {};
    const host = call(bridge.responseJson, JSON.stringify(value), i.status === undefined ? 200 : Number(i.status), headersJson(i.headers));
    return wrapResponse(host);
  }
  get status() { return call(bridge.respStatus, hostResponses.get(this)); }
  get ok() { return call(bridge.respOk, hostResponses.get(this)); }
  get url() { return call(bridge.respUrl, hostResponses.get(this)); }
  get type() { return call(bridge.respType, hostResponses.get(this)); }
  get redirected() { return false; }
  get headers() { return new Headers(JSON.parse(call(bridge.respHeaders, hostResponses.get(this)))); }
  get body() {
    const hostBody = call(bridge.respHasBody, hostResponses.get(this));
    if (!hostBody) return null;
    const host = hostResponses.get(this);
    return { getReader: () => nativeReader(call(bridge.respReader, host)), cancel: () => acall(bridge.respCancel, host) };
  }
  text() { return acall(bridge.respText, hostResponses.get(this)); }
  json() { return this.text().then((t) => JSON.parse(t)); }
}
const wrapResponse = (host) => { const r = Object.create(Response.prototype); hostResponses.set(r, host); return r; };

const hostRequests = new WeakMap();
class Request {
  #headers;
  #method;
  #url;
  constructor(url, init) {
    const i = init || {};
    const host = call(bridge.newRequest, String(url), i.method === undefined ? "GET" : String(i.method), headersJson(i.headers), i.body === undefined || i.body === null ? null : String(i.body));
    hostRequests.set(this, host);
    this.#method = call(bridge.reqMethod, host);
    this.#url = call(bridge.reqUrl, host);
    this.#headers = new Headers(JSON.parse(call(bridge.reqHeaders, host)));
  }
  get method() { return this.#method; }
  get url() { return this.#url; }
  get headers() { return this.#headers; }
  text() { return acall(bridge.reqText, hostRequests.get(this)); }
}

const hostControllers = new WeakMap();
class AbortSignal {
  aborted = false;
  #listeners = [];
  addEventListener(type, fn) { if (type === "abort") this.#listeners.push(fn); }
  removeEventListener(type, fn) { this.#listeners = this.#listeners.filter((f) => f !== fn); }
  dispatchAbort() { this.aborted = true; for (const fn of this.#listeners.splice(0)) fn({ type: "abort" }); }
}
class AbortController {
  constructor() {
    this.signal = new AbortSignal();
    hostControllers.set(this.signal, call(bridge.newAbort));
  }
  abort() {
    if (this.signal.aborted) return;
    call(bridge.abort, hostControllers.get(this.signal));
    this.signal.dispatchAbort();
  }
}

const fetchImpl = async function fetch(url, init) {
  const i = init || {};
  const controller = i.signal ? hostControllers.get(i.signal) : null;
  const host = await acall(bridge.fetch, String(url), i.method === undefined ? null : String(i.method), headersJson(i.headers), i.redirect === undefined ? null : String(i.redirect), controller || null);
  return wrapResponse(host);
};

const timers = new Map();
let nextTimer = 1;
const setTimeoutImpl = function setTimeout(fn, ms) {
  const id = nextTimer++;
  timers.set(id, call(bridge.setTimeout, () => { timers.delete(id); fn(); }, Number(ms) || 0));
  return id;
};
const clearTimeoutImpl = function clearTimeout(id) {
  if (!timers.has(id)) return;
  call(bridge.clearTimeout, timers.get(id));
  timers.delete(id);
};

class TextEncoder {
  get encoding() { return "utf-8"; }
  encode(input) { return toNative(call(bridge.encode, input === undefined ? "" : String(input))); }
}
class TextDecoder {
  #label;
  #fatal;
  constructor(label, options) {
    this.#label = label === undefined ? "utf-8" : String(label);
    this.#fatal = !!(options && options.fatal);
    call(bridge.decode, this.#label, this.#fatal, new Uint8Array(0));
  }
  decode(bytes) { return call(bridge.decode, this.#label, this.#fatal, bytes); }
}

class URL {
  constructor(input, base) {
    const f = JSON.parse(call(bridge.parseUrl, String(input), base === undefined ? null : String(base)));
    for (const k of Object.keys(f)) Object.defineProperty(this, k, { value: f[k], enumerable: true });
  }
  toString() { return this.href; }
  toJSON() { return this.href; }
}

const crypto = { subtle: { digest: async (algorithm, data) => toNative(await acall(bridge.digest, String(algorithm), data)).buffer } };

def("Headers", Headers); def("Response", Response); def("Request", Request);
def("AbortSignal", AbortSignal); def("AbortController", AbortController);
def("fetch", fetchImpl); def("setTimeout", setTimeoutImpl); def("clearTimeout", clearTimeoutImpl);
def("TextEncoder", TextEncoder); def("TextDecoder", TextDecoder); def("URL", URL); def("crypto", crypto);
})`;

/**
 * The production-realm driver: an ES module evaluated INSIDE the realm. It deletes and asserts `Buffer` absent before its
 * first production import, then drives the genuine accepted A/B three-GET paths and the adversarial negatives.
 * The host hooks arrive as one object that the driver captures and removes from the realm global before any import.
 */
const REALM_SOURCE = String.raw`
const H = globalThis.__harness;
delete globalThis.__harness;
const meta = JSON.parse(H.meta());
const order = [];
const enc = new TextEncoder();
const bytes = (obj) => enc.encode(JSON.stringify(obj, null, 2));

// 1. The realm never had a Buffer; delete anyway and prove absence three ways before the first production import.
order.push("delete");
delete globalThis.Buffer;
if (typeof globalThis.Buffer !== "undefined") throw new Error("Buffer still defined");
if (Object.hasOwn(globalThis, "Buffer")) throw new Error("Buffer is an own global property");
if ("Buffer" in globalThis) throw new Error("Buffer is reachable through the global prototype chain");
if (typeof Buffer !== "undefined") throw new Error("Buffer is lexically visible");
order.push("asserted-undefined", "asserted-no-property", "asserted-not-in");

// 2. What can production code see? Everything the realm exposes, and nothing from the host realm.
const RealmObjectProto = Object.prototype;
const probeBuffer = () => ({
  typeofBare: typeof Buffer,
  typeofGlobal: typeof globalThis.Buffer,
  hasOwn: Object.hasOwn(globalThis, "Buffer"),
  inOp: "Buffer" in globalThis,
  descriptor: Object.getOwnPropertyDescriptor(globalThis, "Buffer") === undefined ? null : "present",
  viaFunction: Function("return typeof Buffer")(),
  viaEval: (0, eval)("typeof Buffer"),
  namesInclude: Object.getOwnPropertyNames(globalThis).includes("Buffer"),
  viaThisConstructor: globalThis.constructor.constructor("return typeof Buffer + typeof process")(),
});
const absent = (p) => p.typeofBare === "undefined" && p.typeofGlobal === "undefined" && p.hasOwn === false && p.inOp === false && p.descriptor === null && p.viaFunction === "undefined" && p.viaEval === "undefined" && p.namesInclude === false && p.viaThisConstructor === "undefinedundefined";
const realmPlain = (v) => {
  if (v === null || (typeof v !== "object" && typeof v !== "function")) return true;
  let p = v;
  let last = null;
  while (p !== null) { last = p; p = Object.getPrototypeOf(p); }
  if (last !== RealmObjectProto) return false;
  const ctor = v.constructor;
  if (ctor === undefined) return true;
  try { return ctor.constructor === Function && ctor.constructor("return typeof Buffer")() === "undefined"; } catch { return false; }
};
const leaks = [];
const audit = (label, v) => { if (!realmPlain(v)) leaks.push(label); return v; };
const globals = Object.getOwnPropertyNames(globalThis);
for (const name of meta.bridged) audit("global " + name, globalThis[name]);
audit("crypto.subtle", crypto.subtle);
order.push("realm-audited");

// 3. Only now: cache-fresh imports of the real entrypoint and every production module.
const nonce = String(Date.now()) + "-" + String(Math.random()).slice(2);
const loaded = [];
const fresh = async (file) => {
  const m = await import(H.srcUrl(file) + "?fresh=" + nonce);
  loaded.push(file);
  return m;
};
const index = await fresh("index.js");
const modules = {};
for (const file of ["raw-commit.js", "tree-proof.js", "proof-encoding.js", "output.js", "github.js", "handlers.js", "tools.js", "errors.js", "allowlist.js"]) modules[file] = await fresh(file);
order.push("imported");

const { ENV, OWNER, REPO } = meta;
const { utf8Length, jsonUtf8Length, writeToolResponse, DEGRADED_MAX_BYTES, TIER4_BODY } = modules["output.js"];
const args = (key) => ({ owner: OWNER, repo: REPO, sha: meta[key].commit });
const callRaw = (worker, a, id) => worker.fetch(new Request("https://control.example/mcp/" + ENV.MCP_PATH_SECRET, {
  method: "POST",
  headers: { Authorization: "Bearer " + ENV.MCP_ACCESS_TOKEN, "Content-Type": "application/json" },
  body: JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name: "get_raw_commit", arguments: a } }),
}), ENV);
const gets = () => JSON.parse(H.gets());
const transport = async (key, id, mode, fault) => {
  H.install(key, mode || "normal");
  if (fault) H.setFault(JSON.stringify(fault));
  const response = await callRaw(index.default, args(key), id);
  audit("transport response", response);
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
    gets: gets(),
    ledger: JSON.parse(H.ledger()),
  };
};
const production = async (key, mode) => {
  H.install(key, mode || "normal");
  const result = await modules["raw-commit.js"].getRawCommit(ENV, args(key));
  return { result, gets: gets(), ledger: JSON.parse(H.ledger()) };
};
const attempt = async (fn) => { try { return await fn(); } catch (e) { return { crashed: String(e && e.message) }; } };

const report = { order, loaded, globals, leaks, bufferType: typeof globalThis.Buffer, degradedMax: DEGRADED_MAX_BYTES, tier4Body: TIER4_BODY, realm: probeBuffer() };

report.A = await attempt(() => transport("A", "abc"));
report.B = await attempt(() => transport("B", "abc"));
report.Bnum = await attempt(() => transport("B", 7));

const pa = await production("A");
const pb = await production("B");
const summary = (p) => ({ status: p.result.primary.status, complete: p.result.primary.complete, tree: p.result.primary.tree_sha, commit: p.result.primary.sha, parents: p.result.primary.parents.length, gets: p.gets, primaryBytes: jsonUtf8Length(p.result.primary), degradedBytes: jsonUtf8Length(p.result.degraded) });
report.primaryA = summary(pa);
report.primaryB = summary(pb);
report.ledgers = { transportA: report.A && report.A.ledger, transportB: report.B && report.B.ledger, transportBnum: report.Bnum && report.Bnum.ledger, productionA: pa.ledger, productionB: pb.ledger };

// R375 / F-374-1: genuine fault scenarios through the real product path. Each runs the real getRawCommit (or the real
// transport) against the host router, which records an exact per-request ledger and answers with a faithful response whose
// observable url is the request url, or with a deliberately wrong url, a hung request, or a redirect.
const faulty = async (key, fault) => {
  H.install(key, "normal");
  H.setFault(JSON.stringify(fault));
  let outcome;
  try {
    const r = await modules["raw-commit.js"].getRawCommit(ENV, args(key));
    outcome = { returned: true, status: r.primary.status };
  } catch (e) {
    outcome = { returned: false, errorClass: e && e.class, reason: e && e.details && e.details.reason };
  }
  H.releaseHangs();
  return { outcome, gets: gets(), ledger: JSON.parse(H.ledger()) };
};
report.fidelity = {};
for (const [name, key, fault] of [
  ["urlPath1", "A", { kind: "wrongUrl", at: 1, variant: "path" }],
  ["urlOrigin2", "A", { kind: "wrongUrl", at: 2, variant: "origin" }],
  ["urlQuery3", "B", { kind: "wrongUrl", at: 3, variant: "query" }],
  ["urlQuery3A", "A", { kind: "wrongUrl", at: 3, variant: "query" }],
  ["redirect2", "A", { kind: "redirect", at: 2 }],
  ["hang1", "A", { kind: "hang", at: 1 }],
  ["hang3", "B", { kind: "hang", at: 3 }],
]) report.fidelity[name] = await attempt(() => faulty(key, fault));
report.fidelity.transportUrl = await attempt(async () => { const t = await transport("A", "abc", "normal", { kind: "wrongUrl", at: 2, variant: "path" }); return { error: t.error, hasResult: t.hasResult, id: t.id, gets: t.gets, ledger: t.ledger }; });
report.fidelity.transportHang = await attempt(async () => { const t = await transport("A", "abc", "normal", { kind: "hang", at: 2 }); H.releaseHangs(); return { error: t.error, hasResult: t.hasResult, id: t.id, gets: t.gets, ledger: t.ledger }; });

report.incomplete = await attempt(async () => {
  // Non-COMPLETE primary (genuine RESPONSE_TOO_LARGE from the 2,097,153-byte padded recursive body), no degraded form.
  const over = await production("B", "padded");
  const overText = JSON.stringify({ jsonrpc: "2.0", id: "abc", result: { content: [{ type: "text", text: JSON.stringify(over.result.primary) }] } });
  const overLen = utf8Length(overText);
  const tight = writeToolResponse("abc", over.result, overLen - 1);
  const loose = writeToolResponse("abc", over.result);
  const incomplete = {
    status: over.result.primary.status, reason: over.result.primary.incomplete_reason, degraded: over.result.degraded, gets: over.gets,
    looseTier: loose.tier, looseId: JSON.parse(loose.body).id, tightTier: tight.tier, tightStatus: tight.status, tightId: JSON.parse(tight.body).id,
    tightReason: JSON.parse(tight.body).error.data.reason, tightBytes: utf8Length(tight.body), tightHasResult: JSON.parse(tight.body).result !== undefined,
  };
  const viaTransport = await transport("B", "abc", "padded");
  incomplete.transport = { tier1Status: viaTransport.value && viaTransport.value.status, reason: viaTransport.value && viaTransport.value.reason, id: viaTransport.id, gets: viaTransport.gets };
  return incomplete;
});
report.tier4 = await attempt(async () => {
  // Tier 4: injected tiny ceiling on the real writer with the real A envelope; then through a genuine Response.
  const t4 = writeToolResponse("abc", pa.result, 50);
  const t4response = new Response(t4.body, { status: t4.status, headers: { "content-type": t4.contentType } });
  audit("tier-4 response", t4response);
  return { tier: t4.tier, status: t4.status, contentType: t4.contentType, body: t4.body, responseStatus: t4response.status, responseContentType: t4response.headers.get("content-type"), responseText: await t4response.text() };
});
const extra = await attempt(async () => {
  const t4b = writeToolResponse("abc", pb.result, 50);
  const tier4B = { tier: t4b.tier, status: t4b.status, body: t4b.body };
  const wa = writeToolResponse("abc", pa.result);
  const wb = writeToolResponse("abc", pb.result);
  const writer = { aTier: wa.tier, aBytes: wa.body ? JSON.parse(wa.body).result.content[0].text.length : null, bTier: wb.tier, bId: JSON.parse(wb.body).id };
  return { tier4B, writer };
});
report.tier4B = extra.tier4B;
report.writer = extra.writer;
report.extraCrash = extra.crashed;

// 4. Membrane audit of values production actually receives from the platform (not only the globals).
report.membrane = await attempt(async () => {
  H.install("A", "normal");
  const res = await fetch(H.fetchUrl("A", "commit"), { method: "GET", headers: { Accept: "x" }, redirect: "manual", signal: new AbortController().signal });
  audit("fetch() result", res); audit("fetch() headers", res.headers); audit("fetch() body", res.body);
  const reader = res.body.getReader();
  audit("reader", reader);
  const step = await reader.read();
  audit("read() step", step); audit("chunk", step.value);
  await reader.cancel();
  const u = new URL("/x?y=1", "https://api.github.com");
  audit("URL", u);
  const e = enc.encode("héllo");
  audit("TextEncoder.encode()", e);
  const digest = await crypto.subtle.digest("SHA-256", e);
  audit("digest()", digest); audit("digest() view", new Uint8Array(digest));
  const timer = setTimeout(() => {}, 1);
  clearTimeout(timer);
  let badUrl = null; try { new URL("not a url"); } catch (err) { badUrl = err; }
  let badDecode = null; try { new TextDecoder("utf-8", { fatal: true }).decode(new Uint8Array([0xff, 0xfe])); } catch (err) { badDecode = err; }
  audit("URL error", badUrl); audit("fatal-decode error", badDecode);
  audit("AbortController", new AbortController()); audit("Request", new Request("https://x/", { method: "POST", body: "b" }));
  audit("Headers", new Headers({ a: "b" })); audit("Response", new Response("x", { status: 201 })); audit("Response.json", Response.json({ a: 1 }));
  return { status: res.status, bytes: step.value.length, nativeChunk: step.value instanceof Uint8Array, nativeBuffer: digest instanceof ArrayBuffer, digestBytes: new Uint8Array(digest).length, urlPath: u.pathname + u.search, urlErrorIsTypeError: badUrl instanceof TypeError, decodeErrorIsTypeError: badDecode instanceof TypeError };
});

// 5. Adversarial negatives: no calling context may observe a Buffer value or property.
const spoofs = {};
const namedFunctions = {
  "node:production"() { return probeBuffer(); },
  "node:internal/production": function () { return probeBuffer(); },
};
spoofs.namedFunction = namedFunctions["node:production"]();
spoofs.namedFunction2 = namedFunctions["node:internal/production"]();
Object.defineProperty(namedFunctions["node:production"], "name", { value: "node:production" });
spoofs.renamedFunction = namedFunctions["node:production"]();
spoofs.hostScriptFilename = JSON.parse(H.runNamed("JSON.stringify((" + probeBuffer.toString() + ")())", "node:production"));
spoofs.hostScriptInternalFilename = JSON.parse(H.runNamed("JSON.stringify((" + probeBuffer.toString() + ")())", "node:internal/deps/undici/undici"));
spoofs.getter = ({ get v() { return probeBuffer(); } }).v;
spoofs.asyncAwait = await (async () => { await null; return probeBuffer(); })();
spoofs.asyncTimer = await new Promise((resolve) => setTimeout(() => resolve(probeBuffer()), 0));
spoofs.promiseChain = await Promise.resolve().then(() => probeBuffer());
spoofs.generator = (function* () { yield probeBuffer(); })().next().value;
let reentrant = null;
H.onFetch(() => { reentrant = { probe: probeBuffer(), utf8: utf8Length("é"), nested: modules["output.js"].jsonUtf8Length({ a: 1 }) }; });
report.reentrantRun = await attempt(async () => { const p = await production("A"); return { status: p.result.primary.status, gets: p.gets }; });
H.onFetch(null);
spoofs.reentrantHostCallback = reentrant && reentrant.probe;
report.reentrant = reentrant && { utf8: reentrant.utf8, nested: reentrant.nested };
report.spoofs = Object.fromEntries(Object.entries(spoofs).map(([k, p]) => [k, p === null || p === undefined ? { missing: true } : { absent: absent(p), probe: p }]));
report.realmAfter = probeBuffer();
report.realmAbsentAfter = absent(report.realmAfter);
report.leaks = leaks;
H.report(JSON.stringify(report));
`;

/** The host side: the only code that ever touches the real platform objects. It never mentions Buffer. */
const CHILD_SOURCE = String.raw`
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import { join } from "node:path";
import vm from "node:vm";

const ROOT = process.env.DOGBUILD_ROOT;
const data = JSON.parse(readFileSync(process.env.DOGBUILD_DATA, "utf8"));
const realmSources = JSON.parse(readFileSync(process.env.DOGBUILD_REALM, "utf8"));
const support = await import(pathToFileURL(process.env.DOGBUILD_SUPPORT).href);
const { ENV, GIT, OWNER, REPO, commitBody, treeBody } = support;
const enc = new TextEncoder();
const CAP = 2097152;
const CHUNK = 65536;
const bytes = (obj) => enc.encode(JSON.stringify(obj, null, 2));

// 1. Prepare every genuine fixture response body as plain Uint8Arrays in the HOST realm.
const prepared = {};
for (const key of ["A", "B"]) {
  const fx = data[key];
  const top = fx.entries.filter((e) => !e.path.includes("/"));
  prepared[key] = { fx, commit: bytes(commitBody(fx.commit, fx.tree, fx.parents)), root: bytes(treeBody(fx.tree, top)), rec: bytes(treeBody(fx.tree, fx.entries)) };
}
const paddedRec = new Uint8Array(CAP + 1).fill(32);
paddedRec.set(prepared.B.rec, 0);

// 2. Host-side routing: genuine Node Response objects whose bodies are 64 KiB chunked ReadableStreams.
let getLog = [];
let routes = {};
let onFetch = null;
// highWaterMark 0: the source is pulled only when the consumer reads, so the pull count proves whether a body was parsed.
const streamOf = (body, tally) => {
  let offset = 0;
  return new ReadableStream({
    pull(controller) {
      tally.pulls += 1;
      if (offset >= body.length) { controller.close(); return; }
      const end = Math.min(body.length, offset + CHUNK);
      controller.enqueue(body.subarray(offset, end));
      offset = end;
    },
    cancel() { tally.cancelled = true; },
  }, { highWaterMark: 0 });
};
let ledger = [];
let expectedUrls = [];
let fault = null;
let fastTimers = false;
let hangs = [];
const signalIds = new WeakMap();
let signalSeq = 0;
const API = "https://api.github.com";
const wrongUrlFor = (variant, u) => {
  if (variant === "path") return API + u.pathname.replace(/[0-9a-f]$/, (c) => (c === "0" ? "1" : "0")) + u.search;
  if (variant === "origin") return "https://evil.example" + u.pathname + u.search;
  return API + u.pathname;
};
const hostFetch = async (url, init = {}) => {
  const u = new URL(String(url));
  const n = ledger.length + 1;
  const sig = init.signal;
  const entry = {
    n, method: init.method === undefined ? null : init.method, url: String(url), redirect: init.redirect === undefined ? null : init.redirect,
    signal: sig ? (signalIds.has(sig) ? signalIds.get(sig) : -1) : null, signalAbortedAtCall: sig ? sig.aborted : null,
    violations: [], urlReads: 0, respUrl: null, body: { pulls: 0, cancelled: false }, observedAbort: false, hangGuardFired: false,
  };
  if (entry.method !== "GET") entry.violations.push("method-not-GET");
  if (entry.redirect !== "manual") entry.violations.push("redirect-not-manual");
  if (entry.signal === null || entry.signal === -1) entry.violations.push("signal-missing");
  if (entry.signalAbortedAtCall === true) entry.violations.push("signal-already-aborted");
  if (entry.url !== expectedUrls[n - 1]) entry.violations.push("url-or-order");
  ledger.push(entry);
  getLog.push((init.method ?? "<omitted>") + " " + u.pathname + u.search);
  if (onFetch) onFetch();
  if (entry.violations.length) {
    process.stderr.write("FIDELITY_VIOLATION request " + n + ": " + entry.violations.join(",") + "\n");
    throw new Error("fetch fidelity violation: " + entry.violations.join(","));
  }
  const body = routes[u.pathname + u.search];
  if (!body) throw new Error("unmatched request " + u.pathname + u.search);
  if (fault && fault.at === n && fault.kind === "hang") {
    return new Promise((resolve, reject) => {
      const guard = setTimeout(() => { entry.hangGuardFired = true; reject(new Error("hang guard: forwarded signal never aborted")); }, 5000);
      hangs.push(() => clearTimeout(guard));
      const onAbort = () => { clearTimeout(guard); entry.observedAbort = true; reject(new DOMException("The operation was aborted.", "AbortError")); };
      if (sig.aborted) onAbort(); else sig.addEventListener("abort", onAbort, { once: true });
    });
  }
  if (fault && fault.at === n && fault.kind === "redirect") {
    return new Response(null, { status: 302, headers: { location: API + "/elsewhere" } });
  }
  const response = new Response(streamOf(body, entry.body), { status: 200, headers: { "content-type": "application/json; charset=utf-8" } });
  entry.respUrl = fault && fault.at === n && fault.kind === "wrongUrl" ? wrongUrlFor(fault.variant, u) : String(url);
  // A directly constructed Response has url "": install the observable url a real fetch response carries, and count reads of it.
  Object.defineProperty(response, "url", { get() { entry.urlReads += 1; return entry.respUrl; }, configurable: true });
  return response;
};

// 3. The production realm: a fresh vm context whose sandbox has a null prototype.
const sandbox = Object.create(null);
const ctx = vm.createContext(sandbox);
const baselineGlobals = vm.runInNewContext("Object.getOwnPropertyNames(globalThis)", Object.create(null));
const pairs = (h) => JSON.stringify([...h]);
const bridge = {
  fetch: (url, method, hjson, redirect, ctl) => hostFetch(url, { method: method === null ? undefined : method, headers: JSON.parse(hjson), redirect: redirect === null ? undefined : redirect, signal: ctl ? ctl.signal : undefined }),
  newResponse: (body, status, hjson) => new Response(body, { status, headers: JSON.parse(hjson) }),
  responseJson: (bodyJson, status, hjson) => Response.json(JSON.parse(bodyJson), { status, headers: JSON.parse(hjson) }),
  respStatus: (r) => r.status, respOk: (r) => r.ok, respUrl: (r) => r.url, respType: (r) => r.type,
  respHeaders: (r) => pairs(r.headers), respHasBody: (r) => r.body !== null, respReader: (r) => r.body.getReader(),
  respCancel: (r) => r.body.cancel(), respText: (r) => r.text(),
  readerRead: (rd) => rd.read(), readerCancel: (rd) => rd.cancel(), readerRelease: (rd) => rd.releaseLock(),
  newRequest: (url, method, hjson, body) => new Request(url, { method, headers: JSON.parse(hjson), body: body === null ? undefined : body }),
  reqMethod: (r) => r.method, reqUrl: (r) => r.url, reqHeaders: (r) => pairs(r.headers), reqText: (r) => r.text(),
  encode: (s) => new TextEncoder().encode(s),
  decode: (label, fatal, view) => new TextDecoder(label, { fatal }).decode(view),
  digest: (algorithm, view) => crypto.subtle.digest(algorithm, view).then((ab) => new Uint8Array(ab)),
  setTimeout: (fn, ms) => setTimeout(fn, fastTimers ? 0 : ms), clearTimeout: (handle) => clearTimeout(handle),
  newAbort: () => { const c = new AbortController(); signalIds.set(c.signal, ++signalSeq); return c; }, abort: (c) => c.abort(),
  parseUrl: (input, base) => {
    const u = base === null ? new URL(input) : new URL(input, base);
    return JSON.stringify({ href: u.href, origin: u.origin, protocol: u.protocol, username: u.username, password: u.password, host: u.host, hostname: u.hostname, port: u.port, pathname: u.pathname, search: u.search, hash: u.hash });
  },
};
vm.runInContext(realmSources.bootstrap, ctx, { filename: "realm-bootstrap.js" })(bridge);

let reportJson = null;
const srcUrl = (file) => pathToFileURL(join(ROOT, "src", file)).href;
sandbox.__harness = {
  meta: () => JSON.stringify({ ENV, OWNER, REPO, bridged: realmSources.bridged, A: { commit: prepared.A.fx.commit, tree: prepared.A.fx.tree }, B: { commit: prepared.B.fx.commit, tree: prepared.B.fx.tree } }),
  srcUrl,
  install: (key, mode) => {
    const p = prepared[key];
    routes = {
      [GIT + "/commits/" + p.fx.commit]: p.commit,
      [GIT + "/trees/" + p.fx.tree]: p.root,
      [GIT + "/trees/" + p.fx.tree + "?recursive=1"]: mode === "padded" ? paddedRec : p.rec,
    };
    getLog = [];
    ledger = [];
    fault = null;
    fastTimers = false;
    expectedUrls = [API + GIT + "/commits/" + p.fx.commit, API + GIT + "/trees/" + p.fx.tree, API + GIT + "/trees/" + p.fx.tree + "?recursive=1"];
  },
  setFault: (json) => { fault = JSON.parse(json); fastTimers = fault.kind === "hang"; },
  releaseHangs: () => { for (const release of hangs.splice(0)) release(); fastTimers = false; },
  ledger: () => JSON.stringify(ledger),
  gets: () => JSON.stringify(getLog),
  fetchUrl: (key, which) => "https://api.github.com" + GIT + "/commits/" + prepared[key].fx.commit,
  onFetch: (fn) => { onFetch = fn; },
  runNamed: (code, filename) => String(vm.runInContext(code, ctx, { filename })),
  report: (json) => { reportJson = json; },
};
/*LEAK_HOOK*/

// 4. Evaluate the realm driver as an ES module INSIDE the realm; production modules are linked into the same realm.
const modules = new Map();
const loadModule = (url) => {
  const clean = url.split("?")[0];
  if (!modules.has(clean)) modules.set(clean, new vm.SourceTextModule(readFileSync(fileURLToPath(clean), "utf8"), { context: ctx, identifier: clean, importModuleDynamically }));
  return modules.get(clean);
};
const linker = (specifier, referencing) => loadModule(new URL(specifier, referencing.identifier).href);
async function importModuleDynamically(specifier, referencing) {
  const m = loadModule(new URL(specifier, referencing.identifier).href);
  if (m.status === "unlinked") await m.link(linker);
  if (m.status === "linked") await m.evaluate();
  return m.namespace;
}
const driver = new vm.SourceTextModule(realmSources.driver, { context: ctx, identifier: "file:///realm/driver.mjs", importModuleDynamically });
await driver.link(() => { throw new Error("the realm driver may not import statically"); });
await driver.evaluate();
const report = JSON.parse(reportJson);
report.extraGlobals = report.globals.filter((n) => !baselineGlobals.includes(n)).sort();
console.log(JSON.stringify(report));
`;

const LEAK_HOOKS = {
  "own-property": 'ctx.leak = globalThis[["Buf", "fer"].join("")]; vm.runInContext("Object.defineProperty(globalThis, \'Buf\' + \'fer\', { value: leak, configurable: false }); delete globalThis.leak;", ctx);',
  "inherited-property": 'ctx.leak = globalThis[["Buf", "fer"].join("")]; vm.runInContext("Object.prototype[\'Buf\' + \'fer\'] = leak; delete globalThis.leak;", ctx);',
  "raw-host-class": 'sandbox.TextEncoder = TextEncoder;',
  "raw-host-function": 'sandbox.queueMicrotask = queueMicrotask;',
};

/** Static guards. Both take a source string so that negative controls can feed them deliberately bad sources. */
export function orderViolations(source) {
  const problems = [];
  const del = source.indexOf(MARKER_DELETE);
  const assertAt = source.indexOf(MARKER_ASSERT);
  if (del < 0) problems.push("missing delete statement");
  if (assertAt < 0) problems.push("missing absent assertion");
  if (del >= 0 && assertAt >= 0 && !(del < assertAt)) problems.push("assert precedes delete");
  const gate = assertAt;
  const productionRefs = [...source.matchAll(/\bfresh\(|\bjoin\(ROOT|\bH\.srcUrl\(|\bimport\(|["']src["']|\.\.?\/src\//g)].map((m) => ({ at: m.index, text: m[0] }));
  if (productionRefs.filter((r) => r.text === "fresh(").length < 2) problems.push("too few fresh production imports");
  for (const ref of productionRefs) {
    if (gate < 0 || ref.at < gate) problems.push(`production reference ${JSON.stringify(ref.text)} before the absent assertion`);
  }
  if (/^\s*import\s[^;]*from\s+["'][^"']*src\//m.test(source)) problems.push("static import of production source");
  return problems;
}

const ABSENCE_FORMS = [
  /delete globalThis\.Buffer;/g, /typeof globalThis\.Buffer/g, /typeof Buffer/g, /Object\.hasOwn\(globalThis, "Buffer"\)/g, /"Buffer" in globalThis/g,
  /Object\.getOwnPropertyDescriptor\(globalThis, "Buffer"\)/g, /\.includes\("Buffer"\)/g, /new Error\("Buffer [^"]*"\)/g,
];

/**
 * Rejects any post-delete Buffer definition, accessor, stack-string classifier or disguise.
 * `kind`: "host" (the child process source: no Buffer token at all), "bootstrap" (the membrane: no Buffer token at all, and it
 * may only define the bridged globals) or "driver" (the realm module: only the absence checks themselves may name Buffer).
 */
export function disguiseViolations(source, kind) {
  const problems = [];
  let text = source.replace(/^\s*\/\/.*$/gm, "");
  if (kind === "driver") for (const re of ABSENCE_FORMS) text = text.replace(re, " ");
  if (/\bBuffer\b/.test(text)) problems.push(`${kind}: names Buffer outside the permitted absence checks`);
  if (/\.stack\b|prepareStackTrace|captureStackTrace|\bcaller\b|\bcallee\b/.test(text)) problems.push(`${kind}: stack/caller provenance`);
  if (/\.(?:includes|startsWith|indexOf|match|test)\(\s*["'`/]node:/.test(text) || /\/node:/.test(text)) problems.push(`${kind}: node: classifier`);
  if (/\bProxy\b|__defineGetter__|__defineSetter__|__lookupGetter__|__lookupSetter__|\bReflect\.defineProperty/.test(text)) problems.push(`${kind}: proxy/legacy accessor`);
  if (kind !== "host" && /Object\.defineProperty\(\s*globalThis/.test(text) && kind === "driver") problems.push(`${kind}: defines a global`);
  if (kind === "bootstrap") {
    const defined = [...text.matchAll(/\bdef\("(\w+)"/g)].map((m) => m[1]).sort();
    if (JSON.stringify(defined) !== JSON.stringify([...BRIDGED_GLOBALS].sort())) problems.push(`bootstrap: defines ${defined.join(",")} instead of exactly the bridged globals`);
  }
  return problems;
}

const A_PIN = { commit: "97489121fe43af26b4b527785b326fc87b427471", tree: "32ad195e7dc34e81c76b32ced5320b039c07ae8c", sha256: "313a61297b24d750be89ef6d4db48d75636bc2c644711f31d68e395fd812eeaf" };
const B_PIN = { commit: "906d7ab036de24048075cf177450f1271d0e19ca", tree: "91872b1ea16d1ae7d2c87aed60dd32b3deeb0c0b", sha256: "2159d1c925d2d0b8331c3a40f7d395e91bfedbb8e7709340f2623ffa34edd98b" };
const supportPath = join(root, "test", "raw-support.mjs");
let dataFile = null;
let realmFile = null;
let scratch = null;

function fixtureData() {
  if (dataFile) return dataFile;
  scratch = mkdtempSync(join(tmpdir(), "dogbuild-nobuffer-"));
  dataFile = join(scratch, "fixtures.json");
  realmFile = join(scratch, "realm.json");
  const make = (L1, L2) => {
    const fx = generateGitFixture({ L1, L2, parents: 170 });
    return { commit: fx.commit, tree: fx.tree, parents: fx.parents, entries: fx.entries };
  };
  writeFileSync(dataFile, JSON.stringify({ A: make(100, 100), B: make(122, 127) }));
  writeFileSync(realmFile, JSON.stringify({ bootstrap: REALM_BOOTSTRAP, driver: REALM_SOURCE, bridged: BRIDGED_GLOBALS }));
  return dataFile;
}

function runChild(srcRoot, { leak = null, driver = null } = {}) {
  fixtureData();
  let source = CHILD_SOURCE;
  if (leak) source = source.replace("/*LEAK_HOOK*/", LEAK_HOOKS[leak]);
  let realm = realmFile;
  if (driver) {
    realm = join(scratch, `realm-${Math.random().toString(16).slice(2)}.json`);
    writeFileSync(realm, JSON.stringify({ bootstrap: REALM_BOOTSTRAP, driver, bridged: BRIDGED_GLOBALS }));
  }
  const run = spawnSync(process.execPath, ["--experimental-vm-modules", "--no-warnings", "--input-type=module", "-e", source], {
    encoding: "utf8", maxBuffer: 1 << 26,
    env: { ...process.env, DOGBUILD_ROOT: srcRoot, DOGBUILD_DATA: dataFile, DOGBUILD_SUPPORT: supportPath, DOGBUILD_REALM: realm },
  });
  let report = null;
  try { report = JSON.parse(run.stdout.trim().split("\n").pop()); } catch { /* crash: no report */ }
  return { status: run.status, stderr: run.stderr, report };
}

const SPOOF_CASES = ["namedFunction", "namedFunction2", "renamedFunction", "hostScriptFilename", "hostScriptInternalFilename", "getter", "asyncAwait", "asyncTimer", "promiseChain", "generator", "reentrantHostCallback"];

/** Every acceptance assertion as a list of problems; an empty list means the child proved the accepted behavior. */
function evaluate(run) {
  const problems = [];
  const check = (ok, what) => { if (!ok) problems.push(what); };
  const sec = (name, fn) => { try { fn(); } catch (e) { problems.push(`${name} not evaluable: ${e.message}`); } };
  if (run.status !== 0 || !run.report) {
    const fidelity = String(run.stderr).split("\n").filter((l) => l.startsWith("FIDELITY_VIOLATION")).map((l) => `fetch fidelity: ${l}`);
    return [`child failed (status ${run.status}): ${String(run.stderr).split("\n").find((l) => /Error/.test(l)) || "no report"}`, ...fidelity];
  }
  const r = run.report;
  check(JSON.stringify(r.order) === JSON.stringify(["delete", "asserted-undefined", "asserted-no-property", "asserted-not-in", "realm-audited", "imported"]), "order delete -> assert (typeof, own property, in) -> audit -> import");
  check(r.bufferType === "undefined", "Buffer undefined in the production realm");
  check(["index.js", "raw-commit.js", "tree-proof.js", "proof-encoding.js", "output.js"].every((f) => r.loaded.includes(f)), "all new modules freshly imported");
  check(r.degradedMax === 8192, "DEGRADED_MAX_BYTES 8192");
  check(r.tier4Body === "Output ceiling exceeded", "TIER4_BODY text");
  // true realm isolation: no value, no own property, no inherited property, no escape through constructors
  sec("realm", () => {
    check(JSON.stringify(r.extraGlobals) === JSON.stringify([...BRIDGED_GLOBALS].sort()), `realm exposes exactly the bridged globals, not ${JSON.stringify(r.extraGlobals)}`);
    check(!r.globals.includes("Buffer") && !r.globals.includes("process") && !r.globals.includes("require") && !r.globals.includes("__harness"), "realm global lists no Buffer/process/require/harness");
    check(r.realm.typeofBare === "undefined" && r.realm.typeofGlobal === "undefined", "realm typeof Buffer is undefined");
    check(r.realm.hasOwn === false && r.realm.namesInclude === false && r.realm.descriptor === null, "realm has no own Buffer property");
    check(r.realm.inOp === false, "realm has no inherited Buffer property");
    check(r.realm.viaFunction === "undefined" && r.realm.viaEval === "undefined" && r.realm.viaThisConstructor === "undefinedundefined", "realm constructors and eval reach no Buffer or process");
    check(r.realmAbsentAfter === true, "Buffer still absent after every scenario ran");
    check(Array.isArray(r.leaks) && r.leaks.length === 0, `membrane leaked host-realm objects: ${JSON.stringify(r.leaks)}`);
  });
  // adversarial negatives
  sec("spoofs", () => {
    for (const name of SPOOF_CASES) check(r.spoofs[name] && r.spoofs[name].absent === true, `spoof ${name} observed a Buffer value or property`);
    check(r.reentrantRun && r.reentrantRun.status === "COMPLETE" && r.reentrantRun.gets.length === 3, "re-entrant host callback ran inside a genuine three-GET production call");
    check(r.reentrant && r.reentrant.utf8 === 2 && r.reentrant.nested === 7, "re-entrant callback reached production code");
  });
  sec("membrane", () => {
    const m = r.membrane;
    check(m && !m.crashed && m.status === 200 && m.bytes > 0 && m.nativeChunk === true && m.nativeBuffer === true && m.digestBytes === 32, "membrane delivers genuine status, copied chunk bytes and digest");
    check(m && m.urlPath === "/x?y=1" && m.urlErrorIsTypeError === true && m.decodeErrorIsTypeError === true, "membrane URL and host errors arrive as realm-native values");
  });
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
  sec("fetch fidelity", () => fidelityProblems(r, check));
  return problems;
}

const API_URL = "https://api.github.com";
const urlsFor = (pin) => [`${API_URL}${GIT}/commits/${pin.commit}`, `${API_URL}${GIT}/trees/${pin.tree}`, `${API_URL}${GIT}/trees/${pin.tree}?recursive=1`];

/** R375 / F-374-1: exact method, absolute URL, redirect mode, signal identity and response-URL checks on every routed GET. */
function fidelityProblems(r, check) {
  const pinFor = (name) => (/B/.test(name) ? B_PIN : A_PIN);
  const ledgers = r.ledgers || {};
  for (const [name, ledger] of Object.entries(ledgers)) {
    const want = urlsFor(pinFor(name));
    check(Array.isArray(ledger) && ledger.length === 3, `fetch fidelity ${name}: complete three-request ledger`);
    if (!Array.isArray(ledger)) continue;
    const ids = ledger.map((e) => e.signal);
    check(ledger.every((e, i) => e.n === i + 1 && e.url === want[i]), `fetch fidelity ${name}: exact absolute url and route order commit, root tree, recursive tree`);
    check(ledger.every((e) => e.method === "GET"), `fetch fidelity ${name}: explicit method GET on every request`);
    check(ledger.every((e) => e.redirect === "manual"), `fetch fidelity ${name}: redirect manual on every request`);
    check(ledger.every((e) => Number.isInteger(e.signal) && e.signal > 0 && e.signalAbortedAtCall === false), `fetch fidelity ${name}: a live forwarded abort signal on every request`);
    check(new Set(ids).size === 3, `fetch fidelity ${name}: one distinct abort controller per request`);
    check(ledger.every((e) => e.violations.length === 0), `fetch fidelity ${name}: no host-side violation`);
    check(ledger.every((e) => e.respUrl === e.url && e.respUrl !== ""), `fetch fidelity ${name}: response url is the nonempty exact request url`);
    check(ledger.every((e) => e.urlReads >= 1), `fetch fidelity ${name}: production read the response url (comparison executed) on every request`);
    check(ledger.every((e) => e.body.pulls > 0), `fetch fidelity ${name}: every body was read on the success path`);
  }
  const f = r.fidelity || {};
  const mismatch = (name, at) => {
    const x = f[name];
    check(x && !x.crashed, `fetch fidelity ${name}: scenario crashed ${x && x.crashed}`);
    if (!x || x.crashed) return;
    check(x.outcome && x.outcome.returned === false && x.outcome.errorClass === "UPSTREAM_MALFORMED" && x.outcome.reason === "RESPONSE_URL_MISMATCH", `fetch fidelity ${name}: wrong response url must fail closed RESPONSE_URL_MISMATCH, got ${JSON.stringify(x.outcome)}`);
    check(x.ledger.length === at && x.gets.length === at, `fetch fidelity ${name}: no further GET after the mismatch (got ${x.gets.length})`);
    const last = x.ledger[at - 1];
    check(last && last.urlReads >= 1 && last.respUrl !== last.url && last.body.pulls === 0 && last.body.cancelled === true, `fetch fidelity ${name}: mismatched body never parsed (pulls ${last && last.body.pulls})`);
    check(x.ledger.slice(0, at - 1).every((e) => e.body.pulls > 0 && e.violations.length === 0), `fetch fidelity ${name}: earlier requests succeeded normally`);
  };
  mismatch("urlPath1", 1);
  mismatch("urlOrigin2", 2);
  mismatch("urlQuery3", 3);
  mismatch("urlQuery3A", 3);
  {
    const x = f.redirect2;
    check(x && !x.crashed && x.outcome && x.outcome.returned === false && x.outcome.errorClass === "UPSTREAM_MALFORMED" && x.outcome.reason === "REDIRECT_DENIED" && x.gets.length === 2, `fetch fidelity redirect: a manual-redirect 3xx must fail closed REDIRECT_DENIED, got ${JSON.stringify(x && x.outcome)}`);
  }
  const hang = (name, at) => {
    const x = f[name];
    check(x && !x.crashed, `fetch fidelity ${name}: scenario crashed ${x && x.crashed}`);
    if (!x || x.crashed) return;
    check(x.outcome.returned === false && x.outcome.errorClass === "TIMEOUT" && x.outcome.reason === "REQUEST_TIMEOUT", `fetch fidelity ${name}: bounded abort must classify TIMEOUT REQUEST_TIMEOUT, got ${JSON.stringify(x.outcome)}`);
    const h = x.ledger[at - 1];
    check(x.ledger.length === at && h && h.observedAbort === true && h.hangGuardFired === false, `fetch fidelity ${name}: the host operation did not observe the forwarded signal abort (hang guard ${h && h.hangGuardFired})`);
    check(h && h.violations.length === 0 && h.signal > 0, `fetch fidelity ${name}: hung request carried method, redirect and signal`);
  };
  hang("hang1", 1);
  hang("hang3", 3);
  const tu = f.transportUrl;
  check(tu && !tu.crashed && tu.hasResult === false && tu.id === "abc" && tu.error && tu.error.reason === "RESPONSE_URL_MISMATCH" && tu.gets.length === 2, `fetch fidelity transport: wrong response url through the real transport, got ${JSON.stringify(tu && (tu.error || tu.crashed))}`);
  const th = f.transportHang;
  check(th && !th.crashed && th.hasResult === false && th.id === "abc" && th.error && th.error.errorClass === "TIMEOUT" && th.error.reason === "REQUEST_TIMEOUT" && th.ledger[1] && th.ledger[1].observedAbort === true, `fetch fidelity transport: forwarded abort through the real transport, got ${JSON.stringify(th && (th.error || th.crashed))}`);
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

test("row 24f: static source order - the realm driver deletes and asserts Buffer before any production import", () => {
  assert.deepEqual(orderViolations(REALM_SOURCE), []);
  const del = REALM_SOURCE.indexOf(MARKER_DELETE);
  const absent = REALM_SOURCE.indexOf(MARKER_ASSERT);
  const firstImport = REALM_SOURCE.indexOf("fresh(");
  const entry = REALM_SOURCE.indexOf('fresh("index.js")');
  assert.ok(del > 0 && del < absent && absent < firstImport && firstImport <= entry);
  // the production modules are imported dynamically, never statically, and the whole thing is in this very file
  assert.ok(!/^import .*src\//m.test(REALM_SOURCE));
  const self = readFileSync(fileURLToPath(import.meta.url), "utf8");
  for (const piece of [CHILD_SOURCE, REALM_SOURCE, REALM_BOOTSTRAP]) assert.ok(self.includes(piece.slice(0, 200)));
  // negative controls for the guard itself: an import-first refactor and a missing assertion are both detected
  const importFirst = REALM_SOURCE.replace(MARKER_DELETE, "").replace(MARKER_ASSERT, "").replace("const order = [];", `const order = [];\nconst early = await import(H.srcUrl("output.js"));\n${MARKER_DELETE}\n${MARKER_ASSERT}`);
  assert.notDeepEqual(orderViolations(importFirst), []);
  assert.notDeepEqual(orderViolations(REALM_SOURCE.replace(MARKER_ASSERT, "")), []);
  assert.notDeepEqual(orderViolations(REALM_SOURCE.replace(MARKER_DELETE, "")), []);
  assert.notDeepEqual(orderViolations(`import { x } from "../src/output.js";\n${REALM_SOURCE}`), []);
});

test("row 24f: no stack classifier, post-delete Buffer definition/accessor or other disguise exists in the host, membrane or realm driver", () => {
  assert.deepEqual(disguiseViolations(CHILD_SOURCE, "host"), []);
  assert.deepEqual(disguiseViolations(REALM_BOOTSTRAP, "bootstrap"), []);
  assert.deepEqual(disguiseViolations(REALM_SOURCE, "driver"), []);
  // negative controls: the retired R371 accessor and each equivalent disguise are rejected
  const oldAccessor = 'Object.defineProperty(globalThis, "Buffer", { configurable: true, get() { const caller = (new Error().stack || "").split("\\n")[2] || ""; return caller.includes("node:") ? RealBuffer : undefined; } });';
  assert.notDeepEqual(disguiseViolations(`${REALM_SOURCE}\n${oldAccessor}`, "driver"), []);
  assert.notDeepEqual(disguiseViolations(`${REALM_BOOTSTRAP}\n${oldAccessor}`, "bootstrap"), []);
  assert.notDeepEqual(disguiseViolations(`${CHILD_SOURCE}\n${oldAccessor}`, "host"), []);
  assert.notDeepEqual(disguiseViolations(`${REALM_SOURCE}\nglobalThis.Buffer = class {};`, "driver"), []);
  assert.notDeepEqual(disguiseViolations(`${REALM_SOURCE}\nObject.defineProperty(globalThis, "Buf" + "fer", { value: 1 });\nconst s = new Error().stack;`, "driver"), []);
  assert.notDeepEqual(disguiseViolations(`${REALM_SOURCE}\nconst p = new Proxy({}, {});`, "driver"), []);
  assert.notDeepEqual(disguiseViolations(`${REALM_SOURCE}\nif (x.includes("node:")) y();`, "driver"), []);
  assert.notDeepEqual(disguiseViolations(REALM_BOOTSTRAP.replace('def("URL", URL);', 'def("URL", URL); def("Extra", {});'), "bootstrap"), []);
  assert.notDeepEqual(disguiseViolations(REALM_BOOTSTRAP.replace('def("URL", URL);', 'def("URL", URL); def("Buf" + "fer", 1);').replace('def("crypto", crypto);', 'def("crypto", crypto); globalThis.Buffer = 1;'), "bootstrap"), []);
  // spoofing function names that the harness itself uses as NEGATIVES remain allowed
  assert.deepEqual(disguiseViolations('const f = { "node:production"() { return 1; } };', "driver"), []);
});

test("row 24d: after delete-then-fresh-import in a true isolated realm the real transport serves genuine A (tier 2), B (tier 3), non-COMPLETE (tier 3) and tiny-ceiling (tier 4) over three real GETs", { timeout: 300_000 }, () => {
  const run = baseline();
  assert.deepEqual(evaluate(run), [], run.stderr);
  assert.equal(run.report.A.resultBytes, 8192);
  assert.equal(run.report.primaryB.degradedBytes, 8193);
});

test("row 24d: the production realm has neither a Buffer value nor property and is not an accessor-hidden host global", { timeout: 300_000 }, () => {
  const r = baseline().report;
  assert.deepEqual(r.realm, { typeofBare: "undefined", typeofGlobal: "undefined", hasOwn: false, inOp: false, descriptor: null, viaFunction: "undefined", viaEval: "undefined", namesInclude: false, viaThisConstructor: "undefinedundefined" });
  assert.deepEqual(r.extraGlobals, [...BRIDGED_GLOBALS].sort());
  assert.deepEqual(r.leaks, []);
  assert.equal(r.realmAbsentAfter, true);
});

test("row 24d: ordinary functions named node:production, scripts with node: filenames, getters, async/timer callbacks and re-entrant host callbacks observe no Buffer", { timeout: 300_000 }, () => {
  const r = baseline().report;
  for (const name of SPOOF_CASES) {
    assert.equal(r.spoofs[name].absent, true, `${name}: ${JSON.stringify(r.spoofs[name])}`);
    assert.equal(r.spoofs[name].probe.typeofBare, "undefined");
    assert.equal(r.spoofs[name].probe.hasOwn, false);
    assert.equal(r.spoofs[name].probe.inOp, false);
  }
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
    // accepted order: delete first, in a realm where Buffer genuinely does not exist
    const run = runChild(mutated);
    const problems = evaluate(run);
    assert.notDeepEqual(problems, []);
    assert.match(problems[0], /child failed/);
    assert.match(run.stderr, /Buffer is not defined/);
  } finally { rmSync(mutated, { recursive: true, force: true }); }
});

const MUTATIONS = [
  ["runtime-buffer", "runtime Buffer use in the writer", [["output.js", "export const utf8Length = (text) => UTF8.encode(text).length;", "export const utf8Length = (text) => Buffer.byteLength(text);"]], /scenario crashed|child failed/],
  ["runtime-buffer-serializer", "runtime Buffer use on the success path", [["output.js", "export function serializeResult(id, value) {", "export function serializeResult(id, value) {\n  Buffer.from(\"x\");"]], /Buffer is not defined|A transport tier-2/],
  ["import-time-index", "import-time Buffer use in the entrypoint", [["index.js", "export const SERVER_NAME", "export const __b = Buffer.byteLength(\"x\");\nexport const SERVER_NAME"]], /child failed/],
  ["import-time-tree-proof", "import-time Buffer use in tree-proof", [["tree-proof.js", "\n", "\nglobalThis.Buffer.from(\"x\");\n"]], /child failed/],
  ["presence-in-import", "production insists Buffer is present (\"Buffer\" in globalThis) at import time", [["output.js", "const UTF8 = new TextEncoder();", "const UTF8 = new TextEncoder();\nif (!(\"Buffer\" in globalThis)) throw new Error(\"production requires a Buffer property\");"]], /child failed/],
  ["presence-own-import", "production insists on an own Buffer property at import time", [["output.js", "const UTF8 = new TextEncoder();", "const UTF8 = new TextEncoder();\nif (!Object.hasOwn(globalThis, \"Buffer\")) throw new Error(\"production requires an own Buffer property\");"]], /child failed/],
  ["presence-typeof-runtime", "production insists typeof Buffer is not undefined on the success path", [["output.js", "export function serializeResult(id, value) {", "export function serializeResult(id, value) {\n  if (typeof Buffer === \"undefined\") throw new Error(\"production requires a Buffer value\");"]], /scenario crashed|A transport tier-2/],
  ["presence-descriptor-runtime", "production insists on a Buffer property descriptor in the writer", [["output.js", "export const utf8Length = (text) => UTF8.encode(text).length;", "export const utf8Length = (text) => { if (!Object.getOwnPropertyDescriptor(globalThis, \"Buffer\")) throw new Error(\"production requires a Buffer descriptor\"); return UTF8.encode(text).length; };"]], /scenario crashed|child failed/],
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

// R375 / F-374-1: mutations of the PRODUCT fetch call and response-URL check. Each must be caught by the fidelity proof for its own reason.
const FETCH_CALL = 'fetch(requestUrl, { method: "GET", headers, redirect: "manual", signal: controller.signal }),';
const FETCH_MUTATIONS = [
  ["method-post", "GET changed to POST", [[FETCH_CALL, 'fetch(requestUrl, { method: "POST", headers, redirect: "manual", signal: controller.signal }),']], /method-not-GET|method GET/],
  ["method-omitted", "explicit method omitted", [[FETCH_CALL, 'fetch(requestUrl, { headers, redirect: "manual", signal: controller.signal }),']], /method-not-GET|method GET/],
  ["redirect-follow", "redirect manual changed to follow", [[FETCH_CALL, 'fetch(requestUrl, { method: "GET", headers, redirect: "follow", signal: controller.signal }),']], /redirect-not-manual|redirect manual/],
  ["redirect-omitted", "redirect option removed", [[FETCH_CALL, 'fetch(requestUrl, { method: "GET", headers, signal: controller.signal }),']], /redirect-not-manual|redirect manual/],
  ["signal-omitted", "abort signal omitted", [[FETCH_CALL, 'fetch(requestUrl, { method: "GET", headers, redirect: "manual" }),']], /signal-missing|abort signal/],
  ["signal-substituted", "an unrelated abort signal substituted", [[FETCH_CALL, 'fetch(requestUrl, { method: "GET", headers, redirect: "manual", signal: new AbortController().signal }),']], /hang1|hang3|hang/],
  ["timer-never-aborts", "the timeout timer never aborts the controller", [["const timer = setTimeout(() => controller.abort(), limit);", "const timer = setTimeout(() => {}, limit);"]], /hang1|hang3|hang/],
  ["url-check-removed", "response-URL comparison removed", [['if (typeof response.url === "string" && response.url) {', "if (false) {"]], /read the response url|RESPONSE_URL_MISMATCH/],
  ["url-mismatch-accepted", "a mismatched response URL is accepted", [["if (!same) {", "if (false) {"]], /RESPONSE_URL_MISMATCH/],
  ["url-path-ignored", "pathname dropped from the URL comparison", [["got.origin === want.origin && got.pathname === want.pathname && got.search === want.search", "got.origin === want.origin && got.search === want.search"]], /urlPath1/],
  ["url-origin-ignored", "origin dropped from the URL comparison", [["got.origin === want.origin && got.pathname === want.pathname && got.search === want.search", "got.pathname === want.pathname && got.search === want.search"]], /urlOrigin2/],
  ["url-search-ignored", "query dropped from the URL comparison", [["got.origin === want.origin && got.pathname === want.pathname && got.search === want.search", "got.origin === want.origin && got.pathname === want.pathname"]], /urlQuery3/],
  ["redirect-allowed", "3xx responses no longer rejected", [['if ((status >= 300 && status < 400) || response.type === "opaqueredirect") {', "if (false) {"]], /REDIRECT_DENIED|redirect:/],
];
for (const [label, title, edits, expected] of FETCH_MUTATIONS) {
  test(`R375 mutation ${label}: ${title} fails the VM fetch-fidelity proof`, { timeout: 300_000 }, () => {
    const mutated = mutantRoot(`fx-${label}`, edits.map(([from, to]) => ["github.js", from, to]));
    try {
      const run = runChild(mutated);
      const problems = evaluate(run);
      assert.notDeepEqual(problems, [], `mutation ${label} was not detected`);
      assert.ok(problems.some((p) => expected.test(p)), `unexpected detection for ${label}: ${problems.join(" | ")}`);
    } finally { rmSync(mutated, { recursive: true, force: true }); }
  });
}

test("R375 harness controls: the ledger helper rejects tampered success ledgers and the fixture exposes a nonempty request-identical url", { timeout: 300_000 }, () => {
  const r = structuredClone(baseline().report);
  const problemsOf = (report) => { const out = []; fidelityProblems(report, (ok, what) => { if (!ok) out.push(what); }); return out; };
  assert.deepEqual(problemsOf(r), []);
  const tamper = (fn, expected) => { const t = structuredClone(r); fn(t); assert.ok(problemsOf(t).some((p) => expected.test(p)), `tamper not detected: ${expected}`); };
  tamper((t) => { t.ledgers.productionA[1].method = "POST"; }, /method GET/);
  tamper((t) => { t.ledgers.productionA[2].redirect = "follow"; }, /redirect manual/);
  tamper((t) => { t.ledgers.productionB[0].signal = null; }, /abort signal/);
  tamper((t) => { t.ledgers.productionB[1].signal = t.ledgers.productionB[0].signal; }, /distinct abort controller/);
  tamper((t) => { t.ledgers.transportA[2].url += "&x=1"; }, /exact absolute url/);
  tamper((t) => { t.ledgers.transportB[0].respUrl = ""; }, /nonempty exact request url/);
  tamper((t) => { t.ledgers.transportBnum[0].urlReads = 0; }, /comparison executed/);
  tamper((t) => { t.ledgers.productionA.pop(); }, /three-request ledger/);
  tamper((t) => { t.fidelity.urlOrigin2.outcome = { returned: true, status: "COMPLETE" }; }, /RESPONSE_URL_MISMATCH/);
  tamper((t) => { t.fidelity.hang3.ledger[2].observedAbort = false; }, /did not observe the forwarded signal/);
  for (const e of r.ledgers.productionA) assert.ok(e.respUrl.startsWith("https://api.github.com/") && e.respUrl === e.url);
});

// Harness negative controls: a bridge that leaks the host Buffer, or a host-realm object, into the production realm must be caught.
const LEAK_EXPECTED = {
  "own-property": /child failed/,
  "inherited-property": /child failed/,
  "raw-host-class": /membrane leaked host-realm objects/,
  "raw-host-function": /membrane leaked host-realm objects|realm exposes exactly the bridged globals/,
};
for (const [label, expected] of Object.entries(LEAK_EXPECTED)) {
  test(`row 24c harness control ${label}: a realm bridge that leaks host Buffer semantics is detected`, { timeout: 300_000 }, () => {
    const run = runChild(root, { leak: label });
    const problems = evaluate(run);
    assert.notDeepEqual(problems, [], `bridge leak ${label} was not detected`);
    assert.ok(problems.some((p) => expected.test(p)), `unexpected detection for ${label}: ${problems.join(" | ")}`);
  });
}

test("row 24c harness control: a driver that classifies callers by stack text or recreates a Buffer property is rejected statically and its probes still fail", { timeout: 300_000 }, () => {
  // the retired R371 behavior transplanted into the realm driver: statically rejected ...
  const spoofing = REALM_SOURCE.replace(MARKER_ASSERT, `${MARKER_ASSERT}\nObject.defineProperty(globalThis, "Buffer", { configurable: true, get() { return undefined; } });`);
  assert.notDeepEqual(disguiseViolations(spoofing, "driver"), []);
  // ... and, if it ever ran, the presence probes (own property / in) would flag it
  const run = runChild(root, { driver: spoofing });
  assert.notDeepEqual(evaluate(run), []);
  assert.match(String(run.stderr), /Buffer is an own global property|Buffer/);
});

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
