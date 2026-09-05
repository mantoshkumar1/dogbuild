/**
 * Tool catalogue and capability profiles (DogBuild #164, Strategy 5552709357).
 *
 * `profiles` on each tool is the ONLY source of authority. `tools/list`
 * returns just the caller's profile, and `tools/call` re-checks before
 * dispatch, so a hidden tool is not merely undocumented — it is unreachable.
 *
 * Absent by construction (never a tool, never a handler): merge, auto-merge,
 * ref/branch delete, file delete, comment delete, issue/PR close or reopen,
 * workflow dispatch/rerun/cancel, check or status mutation, review dismissal,
 * approval-as-finalization, secrets, variables, webhooks, environments,
 * deployments, administration, branch-protection mutation, raw log or
 * artifact download, and any general API passthrough.
 */

const repoParams = {
  owner: { type: "string", description: "Repository owner" },
  repo: { type: "string", description: "Repository name" },
};
const R = ["read", "implementor", "reviewer"];
const IMPL = ["implementor"];
const REV = ["reviewer"];
const IMPL_REV = ["implementor", "reviewer"];

function obj(properties, required) {
  return { type: "object", properties, required };
}

export const TOOLS = [
  // ---------------- common reads (every profile) ----------------
  { name: "get_repo", profiles: R, description: "Repository metadata.", inputSchema: obj({ ...repoParams }, ["owner", "repo"]) },
  { name: "list_issues", profiles: R, description: "List issues.", inputSchema: obj({ ...repoParams, state: { type: "string", enum: ["open", "closed", "all"] } }, ["owner", "repo"]) },
  { name: "get_issue", profiles: R, description: "One issue's title, body, state, labels, node id.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" } }, ["owner", "repo", "issue_number"]) },
  { name: "list_issue_comments", profiles: R, description: "Comments on an issue or PR, with ids and updated_at for optimistic concurrency.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" } }, ["owner", "repo", "issue_number"]) },
  { name: "list_labels", profiles: R, description: "Labels defined in the repository.", inputSchema: obj({ ...repoParams }, ["owner", "repo"]) },
  { name: "list_pull_requests", profiles: R, description: "List pull requests.", inputSchema: obj({ ...repoParams, state: { type: "string", enum: ["open", "closed", "all"] } }, ["owner", "repo"]) },
  { name: "get_pull_request", profiles: R, description: "Exact PR identity: state, draft, base/head refs and 40-character SHAs, mergeability, counts.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" } }, ["owner", "repo", "pull_number"]) },
  { name: "list_pull_request_files", profiles: R, description: "Changed files with additions/deletions; set include_patch for diffs. Paginated to completion or explicitly incomplete.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" }, include_patch: { type: "boolean" } }, ["owner", "repo", "pull_number"]) },
  { name: "list_pull_request_commits", profiles: R, description: "Complete PR commit lineage with exact SHAs.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" } }, ["owner", "repo", "pull_number"]) },
  { name: "list_pull_request_reviews", profiles: R, description: "Submitted reviews, each with the commit_id it binds to.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" } }, ["owner", "repo", "pull_number"]) },
  { name: "list_pull_request_review_comments", profiles: R, description: "Inline review comments with path, line, diff hunk and in_reply_to_id.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" } }, ["owner", "repo", "pull_number"]) },
  { name: "list_review_threads", profiles: R, description: "Review threads with isResolved / isOutdated.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" } }, ["owner", "repo", "pull_number"]) },
  { name: "list_branches", profiles: R, description: "Branches and protection flag.", inputSchema: obj({ ...repoParams }, ["owner", "repo"]) },
  { name: "get_branch", profiles: R, description: "One branch and its exact head SHA.", inputSchema: obj({ ...repoParams, branch: { type: "string" } }, ["owner", "repo", "branch"]) },
  { name: "list_commits", profiles: R, description: "Commits on a ref.", inputSchema: obj({ ...repoParams, sha: { type: "string" } }, ["owner", "repo"]) },
  { name: "get_commit", profiles: R, description: "One commit by exact 40-character SHA.", inputSchema: obj({ ...repoParams, sha: { type: "string", description: "Exact 40-character commit SHA" } }, ["owner", "repo", "sha"]) },
  { name: "get_file", profiles: R, description: "Bounded file read at an exact ref. Rejects content above the size limit.", inputSchema: obj({ ...repoParams, path: { type: "string" }, ref: { type: "string" } }, ["owner", "repo", "path"]) },
  { name: "get_commit_ci", profiles: R, description: "THE exact-SHA CI verdict: check-runs, workflow runs, jobs and combined status aggregated with complete pagination, bound to the requested SHA, normalized to pending|success|failure|neutral|unknown. Absent or incomplete evidence is never success.", inputSchema: obj({ ...repoParams, sha: { type: "string", description: "Exact 40-character commit SHA" } }, ["owner", "repo", "sha"]) },
  { name: "list_workflow_run_jobs", profiles: R, description: "Jobs of one workflow run for attempt/identity disambiguation, including failed step names. Metadata only — no raw logs.", inputSchema: obj({ ...repoParams, run_id: { type: "number" }, attempt: { type: "number" } }, ["owner", "repo", "run_id"]) },
  { name: "list_workflow_run_artifacts", profiles: R, description: "Artifact metadata only (name, size, expiry). This Worker never downloads artifact bytes.", inputSchema: obj({ ...repoParams, run_id: { type: "number" } }, ["owner", "repo", "run_id"]) },
  { name: "get_project", profiles: R, description: "Projects-v2 board fields and option ids.", inputSchema: obj({ login: { type: "string" }, project_number: { type: "number" } }, ["login", "project_number"]) },
  { name: "list_project_items", profiles: R, description: "Projects-v2 items with field values.", inputSchema: obj({ login: { type: "string" }, project_number: { type: "number" } }, ["login", "project_number"]) },

  // ---------------- implementor writes ----------------
  { name: "create_issue", profiles: IMPL, description: "Create an issue.", inputSchema: obj({ ...repoParams, title: { type: "string" }, body: { type: "string" }, labels: { type: "array", items: { type: "string" } } }, ["owner", "repo", "title"]) },
  { name: "update_issue", profiles: IMPL, description: "Update issue title, body or labels. Cannot close or reopen.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" }, title: { type: "string" }, body: { type: "string" }, labels: { type: "array", items: { type: "string" } } }, ["owner", "repo", "issue_number"]) },
  { name: "add_labels", profiles: IMPL, description: "Add labels.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" }, labels: { type: "array", items: { type: "string" } } }, ["owner", "repo", "issue_number", "labels"]) },
  { name: "remove_label", profiles: IMPL, description: "Remove one label.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" }, name: { type: "string" } }, ["owner", "repo", "issue_number", "name"]) },
  { name: "add_assignees", profiles: IMPL, description: "Assign users.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" }, assignees: { type: "array", items: { type: "string" } } }, ["owner", "repo", "issue_number", "assignees"]) },
  { name: "remove_assignees", profiles: IMPL, description: "Unassign users.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" }, assignees: { type: "array", items: { type: "string" } } }, ["owner", "repo", "issue_number", "assignees"]) },
  { name: "create_branch", profiles: IMPL, description: "Create the authorized task branch. Protected branch names are refused, and when the role assertion names a branch, only that branch may be created.", inputSchema: obj({ ...repoParams, new_branch: { type: "string" }, from_branch: { type: "string" } }, ["owner", "repo", "new_branch"]) },
  { name: "create_or_update_file", profiles: IMPL, description: "Create or update a file on the authorized task branch only. Never writes to main, master, staging or production.", inputSchema: obj({ ...repoParams, path: { type: "string" }, content: { type: "string" }, message: { type: "string" }, branch: { type: "string" }, sha: { type: "string" } }, ["owner", "repo", "path", "content", "message", "branch"]) },
  { name: "create_pull_request", profiles: IMPL, description: "Open a pull request.", inputSchema: obj({ ...repoParams, title: { type: "string" }, head: { type: "string" }, base: { type: "string" }, body: { type: "string" }, draft: { type: "boolean" } }, ["owner", "repo", "title", "head", "base"]) },
  { name: "update_pull_request", profiles: IMPL, description: "Update PR title, body or base. Cannot close, reopen or merge.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" }, title: { type: "string" }, body: { type: "string" }, base: { type: "string" } }, ["owner", "repo", "pull_number"]) },
  { name: "add_project_item", profiles: IMPL, description: "Add an issue or PR to a Projects-v2 board.", inputSchema: obj({ login: { type: "string" }, project_number: { type: "number" }, content_node_id: { type: "string" } }, ["login", "project_number", "content_node_id"]) },
  { name: "update_project_item_field", profiles: IMPL, description: "Set one Projects-v2 field value.", inputSchema: obj({ login: { type: "string" }, project_number: { type: "number" }, item_id: { type: "string" }, field_id: { type: "string" }, text: { type: "string" }, number: { type: "number" }, date: { type: "string" }, single_select_option_id: { type: "string" } }, ["login", "project_number", "item_id", "field_id"]) },

  // ---------------- shared / reviewer writes ----------------
  { name: "add_issue_comment", profiles: IMPL_REV, description: "Post one bounded comment on an issue or PR. Used for terminal handoff envelopes.", inputSchema: obj({ ...repoParams, issue_number: { type: "number" }, body: { type: "string" } }, ["owner", "repo", "issue_number", "body"]) },
  { name: "update_issue_comment", profiles: IMPL_REV, description: "Edit one identified comment in place with optimistic concurrency. Supply expected_updated_at from list_issue_comments; a stale value is refused before any write. Returns the body digest.", inputSchema: obj({ ...repoParams, comment_id: { type: "number" }, body: { type: "string" }, expected_updated_at: { type: "string", description: "The comment's updated_at as last read. Strongly recommended." } }, ["owner", "repo", "comment_id", "body"]) },
  { name: "publish_review", profiles: REV, description: "Publish exactly one COMMENT review bound to an expected immutable head. The head is re-read immediately before publication and a moved head is refused. Cannot approve, request changes, or dismiss.", inputSchema: obj({ ...repoParams, pull_number: { type: "number" }, expected_head_sha: { type: "string", description: "Exact 40-character head SHA the review binds to" }, body: { type: "string" }, comments: { type: "array", description: "Optional inline findings: [{ path, line, side, body }]", items: { type: "object", properties: { path: { type: "string" }, line: { type: "number" }, side: { type: "string", enum: ["LEFT", "RIGHT"] }, body: { type: "string" } }, required: ["path", "body"] } } }, ["owner", "repo", "pull_number", "expected_head_sha", "body"]) },
];

export function toolsForRole(role) {
  return TOOLS.filter((t) => t.profiles.includes(role)).map(({ profiles, ...rest }) => rest);
}

export function findTool(name) {
  return TOOLS.find((t) => t.name === name) || null;
}
