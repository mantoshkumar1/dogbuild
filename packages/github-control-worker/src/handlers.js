/**
 * Tool dispatch. Order is deliberate and load-bearing:
 *   1. the tool must exist;
 *   2. the caller's server-resolved role must include it;
 *   3. the repository must be on the hard allowlist;
 *   4. the role assertion, when present, must cover that repository;
 *   5. the write target must be inside the assertion's declared scope;
 *   6. only then is any GitHub request issued.
 * A failure at any step happens before a single upstream call is made.
 */
import { ControlError, ErrorClass } from "./errors.js";
import { assertRepoAllowed, assertWritableBranch } from "./allowlist.js";
import { assertAssertionCoversRepo, assertAssertedBranch, assertTargetInScope } from "./roles.js";
import { findTool } from "./tools.js";
import { getCommitCi } from "./ci.js";
import { assertExactSha, gh, ghGraphql, ghPaginate, sha256Hex } from "./github.js";

export const MAX_COMMENT_BODY_BYTES = 60000;
export const MAX_FILE_BYTES = 512000;

function b64encode(str) {
  return btoa(unescape(encodeURIComponent(str)));
}
function b64decode(str) {
  return decodeURIComponent(escape(atob(String(str).replace(/\n/g, ""))));
}

function assertBoundedBody(body) {
  if (typeof body !== "string" || !body.length) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "body is required.");
  }
  const bytes = new TextEncoder().encode(body).length;
  if (bytes > MAX_COMMENT_BODY_BYTES) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `body exceeds the ${MAX_COMMENT_BODY_BYTES}-byte limit.`, {
      bytes,
    });
  }
  return body;
}

/**
 * Every write is bound to a target the signed assertion names, and the check
 * runs BEFORE any upstream request. Signature verification alone is not
 * authorization: it proves the assertion is genuine, not that this particular
 * issue, PR, comment, project or branch is in scope.
 */
function assertWriteScope(name, args, assertion) {
  switch (name) {
    case "update_issue":
    case "add_labels":
    case "remove_label":
    case "add_assignees":
    case "remove_assignees":
    case "add_issue_comment":
      return assertTargetInScope(assertion, "issues", args.issue_number);
    case "update_issue_comment":
      return assertTargetInScope(assertion, "comments", args.comment_id);
    case "update_pull_request":
    case "publish_review":
      return assertTargetInScope(assertion, "pull_requests", args.pull_number);
    case "create_pull_request": {
      const branch = assertAssertedBranch(assertion);
      if (args.head !== branch) {
        throw new ControlError(
          ErrorClass.BRANCH_DENIED,
          `A pull request may only be opened from the authorized branch ('${branch}').`,
          { requested_head: args.head }
        );
      }
      return branch;
    }
    case "create_branch":
    case "create_or_update_file":
      return assertAssertedBranch(assertion);
    case "add_project_item":
    case "update_project_item_field":
      return assertTargetInScope(assertion, "projects", args.project_number);
    case "create_issue":
      if (!assertion || assertion.allow_create_issue !== true) {
        throw new ControlError(
          ErrorClass.TARGET_NOT_IN_SCOPE,
          "Role assertion does not authorize issue creation (allow_create_issue is not true)."
        );
      }
      return true;
    default:
      return null; // reads need no target scope
  }
}

export async function callTool(env, name, args = {}, ctx = {}) {
  const tool = findTool(name);
  if (!tool) throw new ControlError(ErrorClass.UNKNOWN_TOOL, `Unknown tool: ${name}`);

  const role = ctx.role || "read";
  if (!tool.profiles.includes(role)) {
    throw new ControlError(ErrorClass.ROLE_DENIED, `Tool '${name}' is not available to the '${role}' role.`, {
      role,
    });
  }

  const { owner, repo } = args;
  if (owner !== undefined || repo !== undefined) {
    assertRepoAllowed(env, owner, repo);
    assertAssertionCoversRepo(ctx.assertion, owner, repo);
  }

  // Bind the write to an asserted target before any upstream call is made.
  assertWriteScope(name, args, ctx.assertion);

  const base = () => `/repos/${owner}/${repo}`;
  const authorizedBranch = ctx.assertion && ctx.assertion.branch ? ctx.assertion.branch : null;

  switch (name) {
    // ------------------------- common reads -------------------------
    case "get_repo": {
      const d = await gh(env, base());
      return { full_name: d.full_name, private: d.private, default_branch: d.default_branch, html_url: d.html_url };
    }
    case "list_issues": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/issues?state=${args.state || "open"}&per_page=100`);
      return { incomplete, issues: items.map((i) => ({ number: i.number, title: i.title, state: i.state, is_pr: !!i.pull_request, html_url: i.html_url })) };
    }
    case "get_issue": {
      const d = await gh(env, `${base()}/issues/${args.issue_number}`);
      return { number: d.number, title: d.title, state: d.state, body: d.body, labels: (d.labels || []).map((l) => l.name), node_id: d.node_id, updated_at: d.updated_at, html_url: d.html_url };
    }
    case "list_issue_comments": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/issues/${args.issue_number}/comments?per_page=100`);
      return { incomplete, comments: items.map((c) => ({ id: c.id, author: c.user && c.user.login, body: c.body, updated_at: c.updated_at, html_url: c.html_url })) };
    }
    case "list_labels": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/labels?per_page=100`);
      return { incomplete, labels: items.map((l) => ({ name: l.name, color: l.color })) };
    }
    case "list_pull_requests": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/pulls?state=${args.state || "open"}&per_page=100`);
      return { incomplete, pull_requests: items.map((p) => ({ number: p.number, title: p.title, state: p.state, head: p.head && p.head.ref, base: p.base && p.base.ref, html_url: p.html_url })) };
    }
    case "get_pull_request": {
      const d = await gh(env, `${base()}/pulls/${args.pull_number}`);
      return {
        number: d.number, title: d.title, state: d.state, draft: d.draft, body: d.body,
        head_ref: d.head && d.head.ref, head_sha: d.head && d.head.sha,
        base_ref: d.base && d.base.ref, base_sha: d.base && d.base.sha,
        mergeable: d.mergeable, mergeable_state: d.mergeable_state, merged: d.merged,
        commits: d.commits, additions: d.additions, deletions: d.deletions, changed_files: d.changed_files,
        node_id: d.node_id, updated_at: d.updated_at, html_url: d.html_url,
      };
    }
    case "list_pull_request_files": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/pulls/${args.pull_number}/files?per_page=100`);
      return { incomplete, files: items.map((f) => ({ filename: f.filename, status: f.status, additions: f.additions, deletions: f.deletions, changes: f.changes, previous_filename: f.previous_filename, ...(args.include_patch ? { patch: f.patch } : {}) })) };
    }
    case "list_pull_request_commits": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/pulls/${args.pull_number}/commits?per_page=100`);
      return { incomplete, commits: items.map((c) => ({ sha: c.sha, message: c.commit && c.commit.message, author: c.commit && c.commit.author && c.commit.author.name, date: c.commit && c.commit.author && c.commit.author.date })) };
    }
    case "list_pull_request_reviews": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/pulls/${args.pull_number}/reviews?per_page=100`);
      return { incomplete, reviews: items.map((r) => ({ id: r.id, user: r.user && r.user.login, state: r.state, body: r.body, commit_id: r.commit_id, submitted_at: r.submitted_at, html_url: r.html_url })) };
    }
    case "list_pull_request_review_comments": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/pulls/${args.pull_number}/comments?per_page=100`);
      return { incomplete, review_comments: items.map((c) => ({ id: c.id, user: c.user && c.user.login, body: c.body, path: c.path, line: c.line == null ? c.original_line : c.line, side: c.side, commit_id: c.commit_id, in_reply_to_id: c.in_reply_to_id, diff_hunk: c.diff_hunk, html_url: c.html_url })) };
    }
    case "list_review_threads": {
      const query = `query($owner:String!,$repo:String!,$number:Int!){repository(owner:$owner,name:$repo){pullRequest(number:$number){reviewThreads(first:100){nodes{id isResolved isOutdated path line comments(first:50){nodes{databaseId author{login} body createdAt}}}}}}}`;
      const data = await ghGraphql(env, query, { owner, repo, number: args.pull_number });
      const nodes = (((data.repository || {}).pullRequest || {}).reviewThreads || {}).nodes || [];
      return { threads: nodes.map((t) => ({ id: t.id, is_resolved: t.isResolved, is_outdated: t.isOutdated, path: t.path, line: t.line, comments: ((t.comments || {}).nodes || []).map((c) => ({ id: c.databaseId, author: c.author && c.author.login, body: c.body, created_at: c.createdAt })) })) };
    }
    case "list_branches": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/branches?per_page=100`);
      return { incomplete, branches: items.map((b) => ({ name: b.name, sha: b.commit && b.commit.sha, protected: b.protected })) };
    }
    case "get_branch": {
      const d = await gh(env, `${base()}/branches/${encodeURIComponent(args.branch)}`);
      return { name: d.name, sha: d.commit && d.commit.sha, protected: d.protected };
    }
    case "list_commits": {
      const q = args.sha ? `?sha=${encodeURIComponent(args.sha)}&per_page=100` : "?per_page=100";
      const { items, incomplete } = await ghPaginate(env, `${base()}/commits${q}`);
      return { incomplete, commits: items.map((c) => ({ sha: c.sha, message: c.commit && c.commit.message, author: c.commit && c.commit.author && c.commit.author.name })) };
    }
    case "get_commit": {
      assertExactSha(args.sha);
      const d = await gh(env, `${base()}/commits/${args.sha}`);
      if (d.sha && d.sha !== args.sha) {
        throw new ControlError(ErrorClass.HEAD_MISMATCH, "Returned commit does not match the requested SHA.");
      }
      return { sha: d.sha, message: d.commit && d.commit.message, parents: (d.parents || []).map((p) => p.sha), stats: d.stats, files: (d.files || []).map((f) => ({ filename: f.filename, status: f.status, changes: f.changes })), html_url: d.html_url };
    }
    case "get_file": {
      const q = args.ref ? `?ref=${encodeURIComponent(args.ref)}` : "";
      const d = await gh(env, `${base()}/contents/${encodeURIComponent(args.path)}${q}`);
      if (typeof d.size === "number" && d.size > MAX_FILE_BYTES) {
        throw new ControlError(ErrorClass.INVALID_INPUT, `File exceeds the ${MAX_FILE_BYTES}-byte read limit.`, { size: d.size });
      }
      return { path: d.path, sha: d.sha, size: d.size, content: d.encoding === "base64" ? b64decode(d.content) : d.content };
    }
    case "get_commit_ci":
      return getCommitCi(env, { owner, repo, sha: args.sha });
    case "list_workflow_run_jobs": {
      const path = args.attempt
        ? `${base()}/actions/runs/${args.run_id}/attempts/${args.attempt}/jobs?per_page=100`
        : `${base()}/actions/runs/${args.run_id}/jobs?per_page=100`;
      const { items, incomplete } = await ghPaginate(env, path, { itemsKey: "jobs" });
      return { incomplete, run_id: args.run_id, attempt: args.attempt || null, jobs: items.map((j) => ({ id: j.id, name: j.name, status: j.status, conclusion: j.conclusion, html_url: j.html_url, failed_steps: (j.steps || []).filter((s) => s.conclusion && s.conclusion !== "success" && s.conclusion !== "skipped").map((s) => ({ number: s.number, name: s.name, conclusion: s.conclusion })) })) };
    }
    case "list_workflow_run_artifacts": {
      const { items, incomplete } = await ghPaginate(env, `${base()}/actions/runs/${args.run_id}/artifacts?per_page=100`, { itemsKey: "artifacts" });
      return { incomplete, run_id: args.run_id, artifacts: items.map((a) => ({ id: a.id, name: a.name, size_in_bytes: a.size_in_bytes, expired: a.expired, expires_at: a.expires_at, created_at: a.created_at })) };
    }

    // ------------------------- implementor writes -------------------------
    case "create_issue": {
      const d = await gh(env, `${base()}/issues`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: args.title, body: args.body, labels: args.labels }) });
      return { number: d.number, html_url: d.html_url };
    }
    case "update_issue": {
      const payload = {};
      for (const k of ["title", "body", "labels"]) if (args[k] !== undefined) payload[k] = args[k];
      const d = await gh(env, `${base()}/issues/${args.issue_number}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      return { number: d.number, state: d.state, updated_at: d.updated_at, html_url: d.html_url };
    }
    case "add_labels": {
      const d = await gh(env, `${base()}/issues/${args.issue_number}/labels`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ labels: args.labels }) });
      return { labels: d.map((l) => l.name) };
    }
    case "remove_label": {
      await gh(env, `${base()}/issues/${args.issue_number}/labels/${encodeURIComponent(args.name)}`, { method: "DELETE" });
      return { removed: args.name };
    }
    case "add_assignees": {
      const d = await gh(env, `${base()}/issues/${args.issue_number}/assignees`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ assignees: args.assignees }) });
      return { number: d.number, assignees: (d.assignees || []).map((a) => a.login) };
    }
    case "remove_assignees": {
      const d = await gh(env, `${base()}/issues/${args.issue_number}/assignees`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ assignees: args.assignees }) });
      return { number: d.number, assignees: (d.assignees || []).map((a) => a.login) };
    }
    case "create_branch": {
      const newBranch = assertWritableBranch(args.new_branch, authorizedBranch);
      const from = args.from_branch || (await gh(env, base())).default_branch;
      const ref = await gh(env, `${base()}/git/ref/heads/${encodeURIComponent(from)}`);
      const d = await gh(env, `${base()}/git/refs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ref: `refs/heads/${newBranch}`, sha: ref.object.sha }) });
      return { ref: d.ref, sha: d.object && d.object.sha };
    }
    case "create_or_update_file": {
      const branch = assertWritableBranch(args.branch, authorizedBranch);
      const payload = { message: args.message, content: b64encode(args.content), branch };
      if (args.sha) payload.sha = args.sha;
      const d = await gh(env, `${base()}/contents/${encodeURIComponent(args.path)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      return { path: d.content && d.content.path, sha: d.content && d.content.sha, commit_sha: d.commit && d.commit.sha };
    }
    case "create_pull_request": {
      const d = await gh(env, `${base()}/pulls`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: args.title, head: args.head, base: args.base, body: args.body, draft: !!args.draft }) });
      return { number: d.number, head_sha: d.head && d.head.sha, html_url: d.html_url };
    }
    case "update_pull_request": {
      const payload = {};
      for (const k of ["title", "body", "base"]) if (args[k] !== undefined) payload[k] = args[k];
      const d = await gh(env, `${base()}/pulls/${args.pull_number}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      return { number: d.number, state: d.state, updated_at: d.updated_at, html_url: d.html_url };
    }

    // ------------------------- shared / reviewer writes -------------------------
    case "add_issue_comment": {
      assertBoundedBody(args.body);
      const d = await gh(env, `${base()}/issues/${args.issue_number}/comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body: args.body }) });
      return { repo: `${owner}/${repo}`, comment_id: d.id, updated_at: d.updated_at, html_url: d.html_url, body_sha256: await sha256Hex(args.body) };
    }
    case "update_issue_comment": {
      assertBoundedBody(args.body);
      if (typeof args.comment_id !== "number" || !Number.isInteger(args.comment_id)) {
        throw new ControlError(ErrorClass.INVALID_INPUT, "comment_id must be an integer.");
      }
      if (args.expected_updated_at) {
        const current = await gh(env, `${base()}/issues/comments/${args.comment_id}`);
        if (current.id !== args.comment_id) {
          throw new ControlError(ErrorClass.CONFLICT, "Returned comment identity does not match the requested id.");
        }
        if (current.updated_at !== args.expected_updated_at) {
          throw new ControlError(ErrorClass.STALE_VERSION, "Comment changed since it was read; refusing to overwrite.", {
            expected_updated_at: args.expected_updated_at,
            actual_updated_at: current.updated_at,
          });
        }
      }
      const d = await gh(env, `${base()}/issues/comments/${args.comment_id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body: args.body }) });
      if (d.id !== args.comment_id) {
        throw new ControlError(ErrorClass.CONFLICT, "Updated comment identity does not match the requested id.");
      }
      return { repo: `${owner}/${repo}`, comment_id: d.id, updated_at: d.updated_at, html_url: d.html_url, body_sha256: await sha256Hex(args.body) };
    }
    case "publish_review": {
      assertExactSha(args.expected_head_sha);
      assertBoundedBody(args.body);
      const pr = await gh(env, `${base()}/pulls/${args.pull_number}`);
      const currentHead = pr.head && pr.head.sha;
      if (currentHead !== args.expected_head_sha) {
        throw new ControlError(ErrorClass.HEAD_MISMATCH, "PR head moved; refusing to publish a review bound to a stale head.", {
          expected_head_sha: args.expected_head_sha,
          current_head_sha: currentHead,
        });
      }
      const payload = { event: "COMMENT", body: args.body, commit_id: args.expected_head_sha };
      if (Array.isArray(args.comments) && args.comments.length) {
        payload.comments = args.comments.map((c) => ({ path: c.path, body: c.body, ...(c.line !== undefined ? { line: c.line } : {}), ...(c.side ? { side: c.side } : {}) }));
      }
      const d = await gh(env, `${base()}/pulls/${args.pull_number}/reviews`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      return { review_id: d.id, state: d.state, commit_id: d.commit_id, submitted_at: d.submitted_at, html_url: d.html_url, body_sha256: await sha256Hex(args.body) };
    }

    // ------------------------- Projects v2 -------------------------
    case "get_project": {
      const query = `query($login:String!,$number:Int!){user(login:$login){projectV2(number:$number){id title url fields(first:30){nodes{... on ProjectV2FieldCommon{id name dataType} ... on ProjectV2SingleSelectField{id name dataType options{id name}}}}}}}`;
      const data = await ghGraphql(env, query, { login: args.login, number: args.project_number }, env.PROJECT_TOKEN);
      const p = (data.user || {}).projectV2;
      if (!p) throw new ControlError(ErrorClass.NOT_FOUND, "Project not found or not readable with the Projects credential.");
      return { id: p.id, title: p.title, url: p.url, fields: ((p.fields || {}).nodes || []).map((f) => ({ id: f.id, name: f.name, dataType: f.dataType, options: f.options })) };
    }
    case "list_project_items": {
      const query = `query($login:String!,$number:Int!){user(login:$login){projectV2(number:$number){items(first:100){nodes{id content{... on Issue{number title repository{nameWithOwner}} ... on PullRequest{number title repository{nameWithOwner}}} fieldValues(first:20){nodes{... on ProjectV2ItemFieldTextValue{text field{... on ProjectV2FieldCommon{name}}} ... on ProjectV2ItemFieldNumberValue{number field{... on ProjectV2FieldCommon{name}}} ... on ProjectV2ItemFieldDateValue{date field{... on ProjectV2FieldCommon{name}}} ... on ProjectV2ItemFieldSingleSelectValue{name field{... on ProjectV2FieldCommon{name}}}}}}}}}}`;
      const data = await ghGraphql(env, query, { login: args.login, number: args.project_number }, env.PROJECT_TOKEN);
      const items = (((data.user || {}).projectV2 || {}).items || {}).nodes || [];
      return { items: items.map((it) => ({ item_id: it.id, content: it.content, fields: ((it.fieldValues || {}).nodes || []).filter((fv) => fv.field && fv.field.name).map((fv) => ({ field: fv.field.name, value: fv.text != null ? fv.text : fv.number != null ? fv.number : fv.date != null ? fv.date : fv.name })) })) };
    }
    case "add_project_item": {
      const q = `query($login:String!,$number:Int!){user(login:$login){projectV2(number:$number){id}}}`;
      const proj = await ghGraphql(env, q, { login: args.login, number: args.project_number }, env.PROJECT_TOKEN);
      const projectId = ((proj.user || {}).projectV2 || {}).id;
      if (!projectId) throw new ControlError(ErrorClass.NOT_FOUND, "Project not found.");
      const m = `mutation($projectId:ID!,$contentId:ID!){addProjectV2ItemById(input:{projectId:$projectId,contentId:$contentId}){item{id}}}`;
      const d = await ghGraphql(env, m, { projectId, contentId: args.content_node_id }, env.PROJECT_TOKEN);
      return { item_id: ((d.addProjectV2ItemById || {}).item || {}).id };
    }
    case "update_project_item_field": {
      const q = `query($login:String!,$number:Int!){user(login:$login){projectV2(number:$number){id}}}`;
      const proj = await ghGraphql(env, q, { login: args.login, number: args.project_number }, env.PROJECT_TOKEN);
      const projectId = ((proj.user || {}).projectV2 || {}).id;
      if (!projectId) throw new ControlError(ErrorClass.NOT_FOUND, "Project not found.");
      let value;
      if (args.single_select_option_id !== undefined) value = { singleSelectOptionId: args.single_select_option_id };
      else if (args.text !== undefined) value = { text: args.text };
      else if (args.number !== undefined) value = { number: args.number };
      else if (args.date !== undefined) value = { date: args.date };
      else throw new ControlError(ErrorClass.INVALID_INPUT, "Provide one of: text, number, date, single_select_option_id.");
      const m = `mutation($projectId:ID!,$itemId:ID!,$fieldId:ID!,$value:ProjectV2FieldValue!){updateProjectV2ItemFieldValue(input:{projectId:$projectId,itemId:$itemId,fieldId:$fieldId,value:$value}){projectV2Item{id}}}`;
      const d = await ghGraphql(env, m, { projectId, itemId: args.item_id, fieldId: args.field_id, value }, env.PROJECT_TOKEN);
      return { item_id: ((d.updateProjectV2ItemFieldValue || {}).projectV2Item || {}).id };
    }

    default:
      throw new ControlError(ErrorClass.UNKNOWN_TOOL, `Unknown tool: ${name}`);
  }
}
