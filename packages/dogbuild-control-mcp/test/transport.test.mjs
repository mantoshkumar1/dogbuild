import { test } from "node:test";
import assert from "node:assert/strict";
import worker, { MAX_REQUEST_BYTES, SERVER_NAME } from "../src/index.js";
import { ENV, SHA, checkRun, ciRoutes, mockFetch, rpc } from "./helpers.mjs";

test("the MCP path must match exactly", async () => {
  for (const path of ["wrong", `${ENV.MCP_PATH_SECRET}/extra`, `${ENV.MCP_PATH_SECRET}-suffix`]) {
    const response = await rpc("initialize", {}, { path });
    assert.equal(response.status, 404);
  }
});

test("missing server configuration fails closed", async () => {
  for (const key of ["MCP_ACCESS_TOKEN", "GITHUB_TOKEN", "ALLOWED_REPOS"]) {
    const env = { ...ENV };
    delete env[key];
    const response = await rpc("initialize", {}, { env });
    assert.equal(response.status, 503, key);
  }
});

test("weak or malformed server secrets fail closed", async () => {
  for (const env of [
    { ...ENV, MCP_PATH_SECRET: "short" },
    { ...ENV, MCP_PATH_SECRET: "x".repeat(31) },
    { ...ENV, MCP_PATH_SECRET: `${"x".repeat(31)}/` },
    { ...ENV, MCP_ACCESS_TOKEN: "short" },
    { ...ENV, MCP_ACCESS_TOKEN: "x".repeat(31) },
  ]) {
    const response = await rpc("initialize", {}, { env, path: env.MCP_PATH_SECRET, token: env.MCP_ACCESS_TOKEN });
    assert.ok([404, 503].includes(response.status));
  }
});

test("missing or incorrect bearer authentication is rejected", async () => {
  for (const token of ["", "wrong-token"]) {
    const response = await rpc("initialize", {}, { token });
    assert.equal(response.status, 401);
    assert.equal(response.headers.get("www-authenticate"), "Bearer");
  }
});

test("initialize advertises the dedicated server", async () => {
  const response = await rpc("initialize", {});
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.result.serverInfo.name, SERVER_NAME);
  assert.deepEqual(body.result.capabilities, { tools: {} });
});

test("tools/list returns exactly the two reviewed tools", async () => {
  const response = await rpc("tools/list", {});
  const body = await response.json();
  assert.deepEqual(
    body.result.tools.map((tool) => tool.name),
    ["get_commit_ci", "handle_comment_change_request"]
  );
});

test("tools/call traverses the real transport and returns an exact-SHA result", async () => {
  mockFetch(ciRoutes({ checks: [checkRun()] }));
  const response = await rpc("tools/call", {
    name: "get_commit_ci",
    arguments: { owner: "mantoshkumar1", repo: "pingstep", sha: SHA },
  });
  const body = await response.json();
  const value = JSON.parse(body.result.content[0].text);
  assert.equal(value.sha, SHA);
  assert.equal(value.overall, "SUCCESS");
});

test("unknown tools fail at transport with zero GitHub requests", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const response = await rpc("tools/call", {
    name: "update_control_comment",
    arguments: { owner: "mantoshkumar1", repo: "pingstep", sha: SHA },
  });
  const body = await response.json();
  assert.equal(body.error.data.error_class, "UNKNOWN_TOOL");
  assert.equal(calls.length, 0);
});

test("oversized requests are rejected before dispatch", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  const body = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list", padding: "x".repeat(MAX_REQUEST_BYTES) });
  const response = await worker.fetch(new Request(`https://control.example/mcp/${ENV.MCP_PATH_SECRET}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}`, "Content-Type": "application/json" },
    body,
  }), ENV);
  assert.equal(response.status, 400);
  assert.equal(calls.length, 0);
});

test("non-POST requests are rejected after authentication", async () => {
  const response = await worker.fetch(new Request(`https://control.example/mcp/${ENV.MCP_PATH_SECRET}`, {
    method: "GET",
    headers: { Authorization: `Bearer ${ENV.MCP_ACCESS_TOKEN}` },
  }), ENV);
  assert.equal(response.status, 405);
});
