import { assertRepoAllowed } from "./allowlist.js";
import { getCommitCi } from "./ci.js";
import { ControlError, ErrorClass } from "./errors.js";
import { findTool } from "./tools.js";

const INPUT_KEYS = new Set(["owner", "repo", "sha"]);

function assertExactInputShape(args) {
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "Tool arguments must be an object.");
  }
  const extra = Object.keys(args).filter((key) => !INPUT_KEYS.has(key));
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

  assertExactInputShape(args);
  const repository = assertRepoAllowed(env, args.owner, args.repo);

  switch (name) {
    case "get_commit_ci":
      return getCommitCi(env, { owner: repository.owner, repo: repository.repo, sha: args.sha });
    default:
      throw new ControlError(ErrorClass.UNKNOWN_TOOL, `Unknown tool: ${String(name)}`);
  }
}
