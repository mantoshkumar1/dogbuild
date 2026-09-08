import { assertRepoAllowed } from "./allowlist.js";
import { getCommitCi } from "./ci.js";
import { handleCommentChangeRequest } from "./comment-change.js";
import { ControlError, ErrorClass } from "./errors.js";
import { findTool } from "./tools.js";

const INPUT_KEYS = Object.freeze({
  get_commit_ci: new Set(["owner", "repo", "sha"]),
  handle_comment_change_request: new Set([
    "owner",
    "repo",
    "issue_number",
    "original_comment_id",
    "operation",
    "prior_statement",
    "new_statement",
    "evidence_refs",
    "effect",
    "deletion_reason",
  ]),
});

function assertExactInputShape(name, args) {
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "Tool arguments must be an object.");
  }
  const allowed = INPUT_KEYS[name];
  const extra = Object.keys(args).filter((key) => !allowed.has(key));
  if (extra.length) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "Unexpected tool arguments were supplied.", {
      unexpected_fields: extra.sort(),
    });
  }
}

export async function callTool(env, name, args = {}) {
  if (!findTool(name)) {
    throw new ControlError(ErrorClass.UNKNOWN_TOOL, `Unknown tool: ${String(name)}`);
  }

  assertExactInputShape(name, args);
  const repository = assertRepoAllowed(env, args.owner, args.repo);

  switch (name) {
    case "get_commit_ci":
      return getCommitCi(env, { owner: repository.owner, repo: repository.repo, sha: args.sha });
    case "handle_comment_change_request":
      return handleCommentChangeRequest(repository, args);
    default:
      throw new ControlError(ErrorClass.UNKNOWN_TOOL, `Unknown tool: ${String(name)}`);
  }
}
