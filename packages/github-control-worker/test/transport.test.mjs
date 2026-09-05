/**
 * Request-level MCP transport tests (DogBuild #164 correction item 6).
 *
 * These drive the real `export default { fetch }` with real Request objects,
 * so they prove what an actual MCP client sees: which tools are listed, which
 * role the server resolves, and that a denied call never reaches GitHub.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";
import { ROLE_ASSERTION_HEADER } from "../src/roles.js";
import { ENV, SHA, mockFetch, signedAssertion } from "./helpers.mjs";

const URL_OK = `https://worker.invalid/mcp/${ENV.MCP_PATH_SECRET}`;

function rpc(method, params, { assertion = null, url = URL_OK, env = ENV } = {}) {
  const headers = { "content-type": "application/json" };
  if (assertion) headers[ROLE_ASSERTION_HEADER] = assertion;
  return worker.fetch(
    new Request(url, { method: "POST", headers, body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }) }),
    env
  );
}

test("the path secret gates the endpoint", async () => {
  const res = await worker.fetch(new Request("https://worker.invalid/mcp/wrong-secret", { method: "POST", body: "{}" }), ENV);
  assert.equal(res.status, 404);
});

test("initialize advertises the server without any role", async () => {
  const body = await (await rpc("initialize", {})).json();
  assert.equal(body.result.serverInfo.name, "dogbuild-github-control-worker");
});

test("tools/list with no assertion exposes only the read profile", async () => {
  const body = await (await rpc("tools/list", {})).json();
  const names = body.result.tools.map((t) => t.name);
  assert.ok(names.includes("get_commit_ci"), "reads are available");
  assert.ok(!names.includes("update_issue_comment"), "writes are not");
  assert.ok(!names.includes("publish_review"));
  assert.ok(!names.some((n) => n.startsWith("create_")));
});

test("tools/list with an implementor assertion exposes the implementor profile", async () => {
  const assertion = await signedAssertion("implementor", { issues: [1] });
  const body = await (await rpc("tools/list", {}, { assertion })).json();
  const names = body.result.tools.map((t) => t.name);
  assert.ok(names.includes("create_or_update_file"));
  assert.ok(!names.includes("publish_review"), "an implementor is not a reviewer");
});

test("tools/list with a reviewer assertion exposes the reviewer profile", async () => {
  const assertion = await signedAssertion("reviewer", { pull_requests: [165] });
  const body = await (await rpc("tools/list", {}, { assertion })).json();
  const names = body.result.tools.map((t) => t.name);
  assert.ok(names.includes("publish_review"));
  assert.ok(!names.includes("create_or_update_file"), "a reviewer cannot write files");
});

test("an untrusted transport downgrades a valid assertion to read-only", async () => {
  const env = { ...ENV, ROLE_TRANSPORT: undefined };
  const assertion = await signedAssertion("implementor", { issues: [1] });
  const body = await (await rpc("tools/list", {}, { assertion, env })).json();
  const names = body.result.tools.map((t) => t.name);
  assert.ok(!names.includes("update_issue"), "a bearer assertion must not grant writes");

  const calls = mockFetch();
  const call = await (await rpc("tools/call", { name: "update_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 1, body: "x" } }, { assertion, env })).json();
  assert.equal(call.error.data.error_class, "ROLE_DENIED");
  assert.equal(calls.length, 0, "no GitHub request may be issued");
});

test("tools/call rejects a target outside the signed scope before reaching GitHub", async () => {
  const assertion = await signedAssertion("implementor", { issues: [164] });
  const calls = mockFetch();
  const body = await (await rpc("tools/call", { name: "update_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 999, body: "x" } }, { assertion })).json();
  assert.equal(body.error.data.error_class, "TARGET_NOT_IN_SCOPE");
  assert.equal(calls.length, 0);
});

test("tools/call rejects a repository outside the signed assertion", async () => {
  const assertion = await signedAssertion("implementor", { issues: [1] }, { repo: "mantoshkumar1/dogbuild" });
  const calls = mockFetch();
  const body = await (await rpc("tools/call", { name: "update_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 1, body: "x" } }, { assertion })).json();
  assert.equal(body.error.data.error_class, "ROLE_DENIED");
  assert.equal(calls.length, 0);
});

test("tools/call rejects a branch outside the signed assertion", async () => {
  const assertion = await signedAssertion("implementor", { branch: "db-164-authorized" });
  const calls = mockFetch();
  const body = await (await rpc("tools/call", { name: "create_pull_request", arguments: { owner: "mantoshkumar1", repo: "pingstep", title: "t", head: "another-branch", base: "main" } }, { assertion })).json();
  assert.equal(body.error.data.error_class, "BRANCH_DENIED");
  assert.equal(calls.length, 0);
});

test("tools/call rejects an expired assertion before reaching GitHub", async () => {
  const assertion = await signedAssertion("implementor", { issues: [1] }, { exp: Date.now() - 1000 });
  const calls = mockFetch();
  const body = await (await rpc("tools/call", { name: "update_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 1, body: "x" } }, { assertion })).json();
  assert.equal(body.error.data.error_class, "ROLE_DENIED");
  assert.equal(calls.length, 0);
});

test("a tampered assertion is rejected at the transport", async () => {
  const good = await signedAssertion("implementor", { issues: [1] });
  const tampered = `${good.split(".")[0]}.AAAA`;
  const calls = mockFetch();
  const body = await (await rpc("tools/call", { name: "update_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 1, body: "x" } }, { assertion: tampered })).json();
  assert.equal(body.error.data.error_class, "ROLE_DENIED");
  assert.equal(calls.length, 0);
});

test("an in-scope write succeeds through the real transport", async () => {
  const assertion = await signedAssertion("implementor", { issues: [164] });
  const calls = mockFetch({ "PATCH /repos/mantoshkumar1/pingstep/issues/164": { body: { number: 164, state: "open" } } });
  const body = await (await rpc("tools/call", { name: "update_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 164, body: "scoped" } }, { assertion })).json();
  assert.equal(JSON.parse(body.result.content[0].text).number, 164);
  assert.equal(calls.filter((c) => c.method === "PATCH").length, 1);
});

test("a read works with no assertion at all", async () => {
  mockFetch({ "GET /repos/mantoshkumar1/pingstep/issues/1": { body: { number: 1, title: "t", labels: [] } } });
  const body = await (await rpc("tools/call", { name: "get_issue", arguments: { owner: "mantoshkumar1", repo: "pingstep", issue_number: 1 } })).json();
  assert.equal(JSON.parse(body.result.content[0].text).number, 1);
});

test("a caller-supplied role argument changes nothing at the transport", async () => {
  const calls = mockFetch();
  const body = await (await rpc("tools/call", { name: "publish_review", arguments: { owner: "mantoshkumar1", repo: "pingstep", pull_number: 1, expected_head_sha: SHA, body: "x", role: "reviewer" } })).json();
  assert.equal(body.error.data.error_class, "ROLE_DENIED");
  assert.equal(calls.length, 0);
});
