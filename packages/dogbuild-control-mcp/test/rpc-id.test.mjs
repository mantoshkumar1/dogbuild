import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import {
  ENV, GIT, OWNER, REPO, SHA, callRaw, commitBody, hex40, installFetch, installRoutes, jsonResponse, makeTree, smallFlow, flowRoutes,
} from "./raw-support.mjs";
import { mockFetch, ciRoutes, SHA as CI_SHA } from "./helpers.mjs";

const ARGS = { owner: OWNER, repo: REPO, sha: SHA };
const bodyWithId = (token, args = ARGS) =>
  `{"jsonrpc":"2.0","id":${token},"method":"tools/call","params":{"name":"get_raw_commit","arguments":${JSON.stringify(args)}}}`;
const MAX = 524_288;

const presentTokens = [
  "1", "0", "-7", "9007199254740991", "-9007199254740991", '""', '"ordinary"', "null",
  "1e15", "-1e15", "1E+15", "10e14", "5.0", "0.5e1", "0e5", "9.007199254740991e15",
];

test("row 16: present ids are echoed by value and type on success paths", async () => {
  for (const token of presentTokens) {
    installRoutes(smallFlow().routes);
    const response = await callRaw(worker, ARGS, { rawBody: bodyWithId(token) });
    const text = await response.text();
    const parsed = JSON.parse(text);
    assert.equal(response.status, 200, token);
    assert.ok(Object.is(parsed.id, JSON.parse(token)), token);
    assert.equal(typeof parsed.id, typeof JSON.parse(token));
    assert.ok(Buffer.byteLength(text) <= MAX);
    assert.equal(JSON.parse(parsed.result.content[0].text).status, "COMPLETE");
    if (/[eE.]/.test(token) && token !== "null") {
      assert.ok(text.includes(`"id":${JSON.stringify(JSON.parse(token))}`), token);
      assert.ok(!text.includes(`"id":${token}`), token);
    }
  }
});

test("row 16: error-path responses echo the same exact id (upstream 404 and invalid arguments)", async () => {
  for (const token of ["1", '"abc"', "null", "1e15", '""']) {
    installRoutes({ [`${GIT}/commits/${SHA}`]: jsonResponse({ message: "Not Found" }, { status: 404 }) });
    const response = await callRaw(worker, ARGS, { rawBody: bodyWithId(token) });
    const parsed = await response.json();
    assert.ok(Object.is(parsed.id, JSON.parse(token)), token);
    assert.equal(parsed.error.data.error_class, "NOT_FOUND");
    const calls = installRoutes({});
    const bad = await callRaw(worker, { owner: OWNER }, { rawBody: bodyWithId(token, { owner: OWNER }) });
    const badParsed = await bad.json();
    assert.ok(Object.is(badParsed.id, JSON.parse(token)));
    assert.equal(badParsed.error.data.reason, "INVALID_ARGUMENTS");
    assert.equal(calls.length, 0);
  }
});

function bigTreeFlow() {
  const files = [];
  for (let d = 0; d < 5; d += 1) for (let i = 0; i < 1000; i += 1) files.push({ path: `dir${d}/${"n".repeat(50)}${String(i).padStart(4, "0")}`, content: `${d}.${i}` });
  return smallFlow({ files, parents: [hex40(1)] });
}

test("row 16: tier-2 responses (degraded) also carry the exact id and stay under the ceiling", async () => {
  for (const token of ["1", '"abc"', "null", "-1e15", "9007199254740991"]) {
    installRoutes(bigTreeFlow().routes);
    const response = await callRaw(worker, ARGS, { rawBody: bodyWithId(token) });
    const text = await response.text();
    const parsed = JSON.parse(text);
    assert.ok(Buffer.byteLength(text) <= MAX);
    assert.ok(Object.is(parsed.id, JSON.parse(token)), token);
    const value = JSON.parse(parsed.result.content[0].text);
    assert.equal(value.status, "INCOMPLETE");
    assert.equal(value.incomplete_reason, "OUTPUT_CEILING_EXCEEDED");
    assert.equal(value.tree_proof.entries, null);
    assert.equal(value.complete, false);
  }
});

test("row 16/21: the longest ordinary string id that fits a 32,768-byte request is echoed exactly", async () => {
  const frame = bodyWithId('""').length;
  const id = "x".repeat(32_768 - frame);
  const body = bodyWithId(JSON.stringify(id));
  assert.equal(Buffer.byteLength(body), 32_768);
  installRoutes(smallFlow().routes);
  const response = await callRaw(worker, ARGS, { rawBody: body });
  const text = await response.text();
  assert.equal(JSON.parse(text).id, id);
  assert.ok(Buffer.byteLength(text) <= MAX);
  // tier 2 under the same id
  installRoutes(bigTreeFlow().routes);
  const tier2 = await (await callRaw(worker, ARGS, { rawBody: body })).text();
  assert.equal(JSON.parse(tier2).id, id);
  assert.ok(Buffer.byteLength(tier2) <= MAX);
});

test("row 21: the longest escape-heavy string id (fewer than 5,461 units) keeps exact correlation under the ceiling", async () => {
  const frame = bodyWithId('""').length;
  const units = Math.floor((32_768 - frame) / 6);
  assert.ok(units < 5461);
  const id = "\u0001".repeat(units);
  const body = bodyWithId(JSON.stringify(id));
  assert.ok(Buffer.byteLength(body) <= 32_768);
  installRoutes(bigTreeFlow().routes);
  const text = await (await callRaw(worker, ARGS, { rawBody: body })).text();
  assert.equal(JSON.parse(text).id, id);
  assert.ok(Buffer.byteLength(text) <= MAX);
  assert.equal(JSON.parse(JSON.parse(text).result.content[0].text).incomplete_reason, "OUTPUT_CEILING_EXCEEDED");
});

const invalidTokens = [
  "true", "false", "[]", "[1]", "{}", '{"a":1}', "1.5", "1e-1", "9007199254740992", "1e16", "9.007199254740992e15",
  "-0", "-0.0", "-0e5", "1e999", "-1e999",
];

test("row 17: invalid ids are rejected with HTTP 400, id null and zero upstream requests", async () => {
  for (const token of invalidTokens) {
    const calls = installRoutes(smallFlow().routes);
    const response = await callRaw(worker, ARGS, { rawBody: bodyWithId(token) });
    const parsed = await response.json();
    assert.equal(response.status, 400, token);
    assert.equal(parsed.id, null);
    assert.equal(parsed.error.code, -32600);
    assert.equal(parsed.error.data.reason, "INVALID_REQUEST_ID");
    assert.equal(parsed.error.data.error_class, "INVALID_INPUT");
    assert.equal(calls.length, 0, token);
  }
});

test("row 17: the same ids on tools/list and get_commit_ci behave exactly as on main", async () => {
  for (const token of ["true", "[1]", "{}", "1.5", "-0"]) {
    const list = await worker.fetch(new Request(`https://control.example/mcp/${ENV.MCP_PATH_SECRET}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` },
      body: `{"jsonrpc":"2.0","id":${token},"method":"tools/list"}`,
    }), ENV);
    assert.equal(list.status, 200);
    const parsed = await list.json();
    assert.equal(JSON.stringify(parsed.id), JSON.stringify(JSON.parse(token)));
    mockFetch(ciRoutes());
    const ci = await worker.fetch(new Request(`https://control.example/mcp/${ENV.MCP_PATH_SECRET}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` },
      body: `{"jsonrpc":"2.0","id":${token},"method":"tools/call","params":{"name":"get_commit_ci","arguments":{"owner":"mantoshkumar1","repo":"pingstep","sha":"${CI_SHA}"}}}`,
    }), ENV);
    assert.equal(ci.status, 200);
    assert.equal(JSON.stringify((await ci.json()).id), JSON.stringify(JSON.parse(token)));
  }
});

test("the tools/list descriptor for get_raw_commit is strict and states the id requirement", async () => {
  const response = await worker.fetch(new Request(`https://control.example/mcp/${ENV.MCP_PATH_SECRET}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` },
    body: '{"jsonrpc":"2.0","id":1,"method":"tools/list"}',
  }), ENV);
  const tool = (await response.json()).result.tools.find((t) => t.name === "get_raw_commit");
  assert.equal(tool.inputSchema.additionalProperties, false);
  assert.deepEqual(tool.inputSchema.required, ["owner", "repo", "sha"]);
  assert.match(tool.description, /id member/);
  void [installFetch, makeTree, commitBody, flowRoutes];
});
