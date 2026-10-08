import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { ENV, OWNER, REPO, SHA, callRaw, installRoutes, smallFlow } from "./raw-support.mjs";
import { mockFetch, ciRoutes, SHA as CI_SHA } from "./helpers.mjs";

const ARGS = { owner: OWNER, repo: REPO, sha: SHA };
const noId = (args) => `{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_raw_commit","arguments":${JSON.stringify(args)}}}`;

async function assertNotification(response) {
  assert.equal(response.status, 202);
  assert.equal(await response.text(), "");
  assert.equal(response.headers.get("content-type"), null);
}

test("row 18: an id-less get_raw_commit call is a silent 202 with zero GETs", async () => {
  const calls = installRoutes(smallFlow().routes);
  await assertNotification(await callRaw(worker, ARGS, { omitId: true }));
  assert.equal(calls.length, 0);
});

test("row 18: bad, extra, disallowed and missing arguments are still silent when the id is absent", async () => {
  const cases = [
    { owner: OWNER, repo: REPO },
    { ...ARGS, extra: "SENTINEL_SECRET_VALUE" },
    { owner: "someone", repo: "else", sha: SHA },
    { owner: OWNER, repo: REPO, sha: "A".repeat(40) },
  ];
  for (const args of cases) {
    const calls = installRoutes({});
    await assertNotification(await callRaw(worker, args, { omitId: true }));
    assert.equal(calls.length, 0);
  }
  const calls = installRoutes({});
  const omitted = await callRaw(worker, null, {
    rawBody: '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_raw_commit"}}',
  });
  await assertNotification(omitted);
  assert.equal(calls.length, 0);
});

test("row 18: controls - with an id the same request runs, and earlier gates are unchanged", async () => {
  const calls = installRoutes(smallFlow().routes);
  const ok = await callRaw(worker, ARGS, { id: 1 });
  assert.equal(ok.status, 200);
  assert.equal(calls.length, 3);

  const url = `https://control.example/mcp/${ENV.MCP_PATH_SECRET}`;
  const body = noId(ARGS);
  const unauth = await worker.fetch(new Request(url, { method: "POST", body }), ENV);
  assert.equal(unauth.status, 401);
  const wrongMethod = await worker.fetch(new Request(url, { method: "GET", headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` } }), ENV);
  assert.equal(wrongMethod.status, 405);
  const wrongPath = await worker.fetch(new Request(`${url}x`, { method: "POST", headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` }, body }), ENV);
  assert.equal(wrongPath.status, 404);
  const oversized = await worker.fetch(new Request(url, {
    method: "POST", headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` },
    body: noId({ ...ARGS, pad: "x".repeat(40_000) }),
  }), ENV);
  assert.equal(oversized.status, 400);
});

test("row 18: scope - other tools and unknown names keep the null-id default; near-miss names are not notifications", async () => {
  mockFetch(ciRoutes());
  const post = (payload) => worker.fetch(new Request(`https://control.example/mcp/${ENV.MCP_PATH_SECRET}`, {
    method: "POST", headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` }, body: JSON.stringify(payload),
  }), ENV);
  const ci = await post({ jsonrpc: "2.0", method: "tools/call", params: { name: "get_commit_ci", arguments: { owner: "mantoshkumar1", repo: "pingstep", sha: CI_SHA } } });
  assert.equal(ci.status, 200);
  assert.equal((await ci.json()).id, null);
  const unknown = await post({ jsonrpc: "2.0", method: "tools/call", params: { name: "no_such_tool", arguments: {} } });
  assert.equal((await unknown.json()).id, null);
  for (const name of ["get_raw_commit ", "Get_Raw_Commit", "GET_RAW_COMMIT"]) {
    const response = await post({ jsonrpc: "2.0", method: "tools/call", params: { name, arguments: ARGS } });
    assert.equal(response.status, 200);
    const parsed = await response.json();
    assert.equal(parsed.id, null);
    assert.equal(parsed.error.data.error_class, "UNKNOWN_TOOL");
  }
  const list = await post({ jsonrpc: "2.0", method: "tools/list" });
  assert.equal((await list.json()).id, null);
});

test("row 19: an explicit null id is a request with a null id", async () => {
  const calls = installRoutes(smallFlow().routes);
  const response = await callRaw(worker, ARGS, { id: null });
  const parsed = await response.json();
  assert.equal(response.status, 200);
  assert.ok(Object.is(parsed.id, null));
  assert.ok(Object.prototype.hasOwnProperty.call(parsed, "id"));
  assert.equal(calls.length, 3);

  const failing = installRoutes({});
  const bad = await (await callRaw(worker, { owner: OWNER }, { id: null })).json();
  assert.ok(Object.is(bad.id, null));
  assert.equal(bad.error.data.reason, "INVALID_ARGUMENTS");
  assert.equal(failing.length, 0);
});

test("row 19: the id-less and null-id requests differ in status, body and GET count", async () => {
  const withNull = installRoutes(smallFlow().routes);
  const a = await callRaw(worker, ARGS, { id: null });
  const withoutId = installRoutes(smallFlow().routes);
  const b = await callRaw(worker, ARGS, { omitId: true });
  assert.notEqual(a.status, b.status);
  assert.notEqual(await a.text(), await b.text());
  assert.notEqual(withNull.length, withoutId.length);
});

test("row 18: a notification never contains an id, result or error token", async () => {
  installRoutes({});
  const response = await callRaw(worker, ARGS, { omitId: true });
  const text = await response.text();
  for (const token of ['"id":null', '"result"', '"error"']) assert.ok(!text.includes(token));
});
