import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { ErrorClass } from "../src/errors.js";
import { callTool } from "../src/handlers.js";
import { findTool, TOOLS } from "../src/tools.js";
import { ENV, SHA, ciRoutes, mockFetch } from "./helpers.mjs";

const LEGACY_AND_FORBIDDEN = [
  "get_repo", "list_issues", "get_issue", "list_issue_comments", "list_labels",
  "list_pull_requests", "get_pull_request", "list_pull_request_files",
  "list_pull_request_commits", "list_pull_request_reviews",
  "list_pull_request_review_comments", "list_review_threads", "list_branches",
  "get_branch", "list_commits", "get_commit", "get_file",
  "list_workflow_run_jobs", "list_workflow_run_artifacts", "get_project",
  "list_project_items", "create_issue", "update_issue", "add_labels",
  "remove_label", "add_assignees", "remove_assignees", "create_branch",
  "create_or_update_file", "create_pull_request", "update_pull_request",
  "add_project_item", "update_project_item_field", "add_issue_comment",
  "update_issue_comment", "update_control_comment", "publish_review",
  "correct_own_comment", "edit_comment", "delete_comment", "delete_issue_comment",
  "merge_pull_request", "dispatch_workflow", "rerun_workflow", "get_job_logs",
];

test("the reviewed catalogue exposes exactly two non-mutating tools", () => {
  assert.deepEqual(TOOLS.map((tool) => tool.name), ["get_commit_ci", "handle_comment_change_request"]);
  assert.equal(findTool("get_commit_ci").inputSchema.additionalProperties, false);
  assert.deepEqual(findTool("get_commit_ci").inputSchema.required, ["owner", "repo", "sha"]);
  assert.equal(findTool("handle_comment_change_request").inputSchema.additionalProperties, false);
  assert.deepEqual(
    findTool("handle_comment_change_request").inputSchema.required,
    ["owner", "repo", "issue_number", "original_comment_id", "operation"]
  );
});

test("every legacy, parked, generic, destructive and random name is unreachable", async () => {
  const calls = mockFetch({}, { unmatched: "throw" });
  for (const name of [...LEGACY_AND_FORBIDDEN, "GET_COMMIT_CI", "get_Commit_ci", "random_tool"]) {
    await assert.rejects(
      callTool(ENV, name, { owner: "mantoshkumar1", repo: "pingstep", sha: SHA }),
      (error) => error.class === ErrorClass.UNKNOWN_TOOL,
      name
    );
  }
  assert.equal(calls.length, 0);
});

test("the only reachable handler issues GET requests only", async () => {
  const calls = mockFetch(ciRoutes());
  await callTool(ENV, "get_commit_ci", { owner: "mantoshkumar1", repo: "pingstep", sha: SHA });
  assert.ok(calls.length >= 4);
  assert.deepEqual([...new Set(calls.map((call) => call.method))], ["GET"]);
});

test("source has no parked handler, browser automation or local process surface", () => {
  const sourceDir = join(dirname(fileURLToPath(import.meta.url)), "..", "src");
  const sources = readdirSync(sourceDir)
    .filter((name) => name.endsWith(".js"))
    .map((name) => `${name}\n${readFileSync(join(sourceDir, name), "utf8")}`)
    .join("\n");
  for (const forbidden of [
    /update_control_comment/i, /correct_own_comment/i, /delete_comment/i,
    /playwright/i, /puppeteer/i, /chrom(?:e|ium)/i, /webdriver/i, /selenium/i,
    /child_process/i, /\bspawn\s*\(/i, /\bexecSync\s*\(/i,
  ]) {
    assert.doesNotMatch(sources, forbidden);
  }
});
