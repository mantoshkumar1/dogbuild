/**
 * Hard repository allowlist (DogBuild #164 invariant 1).
 *
 * Unset or malformed configuration denies everything. There is deliberately
 * no "unset means unrestricted" path: that was the defect found in the
 * reference draft during the capability audit.
 */
import { ControlError, ErrorClass } from "./errors.js";

const REPO_RE = /^[A-Za-z0-9._-]+\/[A-Za-z0-9._-]+$/;

export function parseAllowlist(env) {
  const raw = env && typeof env.ALLOWED_REPOS === "string" ? env.ALLOWED_REPOS.trim() : "";
  if (!raw) {
    throw new ControlError(ErrorClass.CONFIG_INVALID, "ALLOWED_REPOS is not configured; all repositories are denied.");
  }
  const entries = raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (!entries.length || !entries.every((e) => REPO_RE.test(e))) {
    throw new ControlError(ErrorClass.CONFIG_INVALID, "ALLOWED_REPOS is malformed; all repositories are denied.");
  }
  return entries.map((e) => e.toLowerCase());
}

export function assertRepoAllowed(env, owner, repo) {
  const allowed = parseAllowlist(env);
  if (typeof owner !== "string" || typeof repo !== "string" || !owner || !repo) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "owner and repo are required.");
  }
  const requested = `${owner}/${repo}`.toLowerCase();
  if (!allowed.includes(requested)) {
    throw new ControlError(ErrorClass.ALLOWLIST_DENIED, `Repository not on the allowlist: ${owner}/${repo}`);
  }
}

/** Branches this Worker must never write to, in any profile. */
export const PROTECTED_BRANCHES = ["main", "master", "staging", "production"];

export function assertWritableBranch(branch, authorizedBranch) {
  if (typeof branch !== "string" || !branch.trim()) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "branch is required for this operation.");
  }
  const b = branch.trim();
  if (PROTECTED_BRANCHES.includes(b.toLowerCase())) {
    throw new ControlError(ErrorClass.BRANCH_DENIED, `Direct writes to '${b}' are never permitted through this Worker.`);
  }
  if (authorizedBranch && b !== authorizedBranch) {
    throw new ControlError(
      ErrorClass.BRANCH_DENIED,
      `Branch '${b}' is not the branch authorized for this task ('${authorizedBranch}').`
    );
  }
  return b;
}
