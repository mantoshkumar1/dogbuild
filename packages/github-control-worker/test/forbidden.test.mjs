import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { TOOLS, findTool, toolsForRole } from "../src/tools.js";
import { callTool } from "../src/handlers.js";
import { ErrorClass } from "../src/errors.js";
import { ENV, SHA, OTHER_SHA, ctxFor, mockFetch } from "./helpers.mjs";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
const sources = readdirSync(SRC).filter((f) => f.endsWith(".js")).map((f) => ({ file: f, text: readFileSync(join(SRC, f), "utf8") }));

test("forbidden capabilities are absent as tools, not merely undocumented", () => {
  const forbidden = [
    "merge_pull_request", "delete_branch", "delete_file", "delete_issue_comment",
    "rerun_workflow", "dispatch_workflow", "cancel_workflow", "create_deployment",
    "update_secret", "set_secret", "dismiss_review", "update_branch_protection",
    "get_job_logs", "download_artifact", "search_code", "search_issues",
  ];
  const names = TOOLS.map((t) => t.name);
  for (const f of forbidden) {
    assert.ok(!names.includes(f), `${f} must not exist`);
    assert.equal(findTool(f), null);
  }
});

test("calling a forbidden tool by name returns UNKNOWN_TOOL and issues no request", async () => {
  const calls = mockFetch();
  for (const name of ["merge_pull_request", "delete_file", "delete_issue_comment", "rerun_workflow"]) {
    await assert.rejects(
      callTool(ENV, name, { owner: "mantoshkumar1", repo: "pingstep" }, { role: "implementor" }),
      (e) => e.class === ErrorClass.UNKNOWN_TOOL
    );
  }
  assert.equal(calls.length, 0);
});

test("no schema exposes issue/PR state, so nothing can close or reopen", () => {
  for (const t of TOOLS) {
    const props = Object.keys(t.inputSchema.properties || {});
    if (t.name === "list_issues" || t.name === "list_pull_requests") continue; // filter only
    assert.ok(!props.includes("state"), `${t.name} must not accept a state field`);
  }
});

test("publish_review can only ever submit COMMENT", async () => {
  const tool = findTool("publish_review");
  assert.ok(!JSON.stringify(tool.inputSchema).includes("APPROVE"));
  assert.ok(!JSON.stringify(tool.inputSchema).includes("REQUEST_CHANGES"));
  const calls = mockFetch({
    "GET /repos/mantoshkumar1/pingstep/pulls/1": { body: { head: { sha: SHA } } },
    "POST /repos/mantoshkumar1/pingstep/pulls/1/reviews": { body: { id: 7, state: "COMMENTED", commit_id: SHA } },
  });
  const ctx = await ctxFor("reviewer", { pull_requests: [1] });
  await callTool(ENV, "publish_review", { owner: "mantoshkumar1", repo: "pingstep", pull_number: 1, expected_head_sha: SHA, body: "b", event: "APPROVE" }, ctx);
  const post = calls.find((c) => c.method === "POST");
  assert.equal(post.body.event, "COMMENT", "an argument-supplied event must not become an approval");
  assert.equal(post.body.commit_id, SHA);
});

test("a moved head rejects before the review is published", async () => {
  const calls = mockFetch({ "GET /repos/mantoshkumar1/pingstep/pulls/1": { body: { head: { sha: OTHER_SHA } } } });
  await assert.rejects(
    callTool(ENV, "publish_review", { owner: "mantoshkumar1", repo: "pingstep", pull_number: 1, expected_head_sha: SHA, body: "b" }, await ctxFor("reviewer", { pull_requests: [1] })),
    (e) => e.class === ErrorClass.HEAD_MISMATCH
  );
  assert.equal(calls.filter((c) => c.method === "POST").length, 0);
});

test("no source file references a browser or GUI automation surface", () => {
  const banned = [/playwright/i, /puppeteer/i, /chrome/i, /chromium/i, /webdriver/i, /selenium/i, /claude-in-chrome/i, /accessibility.?tree/i];
  for (const { file, text } of sources) {
    for (const re of banned) {
      assert.ok(!re.test(text), `${file} must not reference ${re}`);
    }
  }
});

test("no source file spawns a local process", () => {
  const banned = [/child_process/, /node:child_process/, /\bspawn\(/, /\bexecSync\(/, /npm exec/];
  for (const { file, text } of sources) {
    for (const re of banned) assert.ok(!re.test(text), `${file} must not spawn processes (${re})`);
  }
});

test("no handler can reach a destructive or privileged endpoint", async () => {
  const seen = [];
  globalThis.fetch = async (url, init = {}) => {
    seen.push(`${(init.method || "GET").toUpperCase()} ${String(url)}`);
    return { ok: true, status: 200, headers: { get: () => null }, text: async () => JSON.stringify({ id: 1, sha: SHA, head: { sha: SHA }, check_runs: [], workflow_runs: [], jobs: [], artifacts: [], statuses: [], state: "success", commit: {}, object: { sha: SHA }, content: {}, default_branch: "main", assignees: [], labels: [] }) };
  };
  const argsFor = (t) => {
    const a = {};
    for (const k of t.inputSchema.required || []) {
      const p = (t.inputSchema.properties || {})[k] || {};
      if (k === "owner") a[k] = "mantoshkumar1";
      else if (k === "repo") a[k] = "pingstep";
      else if (k === "sha" || k === "expected_head_sha") a[k] = SHA;
      else if (k === "branch" || k === "new_branch") a[k] = "db-164-task-branch";
      else if (p.type === "number") a[k] = 1;
      else if (p.type === "array") a[k] = ["x"];
      else a[k] = "x";
    }
    if (t.name === "create_or_update_file") a.branch = "db-164-task-branch";
    if (t.name === "update_project_item_field") a.text = "v";
    return a;
  };
  const scopes = { issues: [1], pull_requests: [1], comments: [1], projects: [1], branch: "db-164-task-branch", allow_create_issue: true };
  const ctxCache = {
    read: await ctxFor("implementor", scopes),
    implementor: await ctxFor("implementor", scopes),
    reviewer: await ctxFor("reviewer", scopes),
  };
  for (const t of TOOLS) {
    try {
      await callTool(ENV, t.name, argsFor(t), ctxCache[t.profiles[0]]);
    } catch {
      /* shape errors from the generic mock are fine; we only audit the requests */
    }
  }
  const forbiddenPatterns = [
    [/^DELETE .*\/git\/refs/, "ref deletion"],
    [/^DELETE .*\/contents/, "file deletion"],
    [/^DELETE .*\/issues\/comments/, "comment deletion"],
    [/^PUT .*\/pulls\/\d+\/merge/, "merge"],
    [/rerun|dispatches|cancel/, "workflow mutation"],
    [/\/deployments|\/environments|\/actions\/secrets|\/actions\/variables/, "privileged surface"],
    [/\/actions\/jobs\/\d+\/logs|\/artifacts\/\d+\/zip/, "raw log or artifact download"],
  ];
  for (const [re, label] of forbiddenPatterns) {
    const hit = seen.find((s) => re.test(s));
    assert.equal(hit, undefined, `no handler may reach ${label} (saw: ${hit})`);
  }
});

test("every tool belongs to at least one profile and every profile is reachable", () => {
  assert.ok(toolsForRole("read").length > 0);
  assert.ok(toolsForRole("implementor").length > toolsForRole("read").length);
  assert.ok(toolsForRole("reviewer").length > toolsForRole("read").length);
  assert.equal(new Set(TOOLS.map((t) => t.name)).size, TOOLS.length, "tool names must be unique");
});
