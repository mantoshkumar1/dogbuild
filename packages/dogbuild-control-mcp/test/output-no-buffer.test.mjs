import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

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
