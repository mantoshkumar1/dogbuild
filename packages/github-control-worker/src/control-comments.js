/**
 * Configuration-pinned control comments.
 *
 * The status slot a scheduled worker rewrites every wake is a fixed, tiny set
 * of comments. Binding that set in Worker CONFIGURATION — not in a
 * caller-supplied argument and not in a role assertion — lets the one write a
 * headless worker genuinely needs stay available while the trusted identity
 * transport is still blocked (see CAPABILITY_BLOCKED_ROLE_TRANSPORT).
 *
 * Format: CONTROL_COMMENTS = "owner/repo#commentId,owner/repo#commentId"
 * Unset or malformed denies every control-comment write. There is no
 * "unset means unrestricted" path.
 */
import { ControlError, ErrorClass } from "./errors.js";

const ENTRY_RE = /^([A-Za-z0-9._-]+)\/([A-Za-z0-9._-]+)#(\d+)$/;

export function parseControlComments(env) {
  const raw = env && typeof env.CONTROL_COMMENTS === "string" ? env.CONTROL_COMMENTS.trim() : "";
  if (!raw) {
    throw new ControlError(
      ErrorClass.CONTROL_TARGET_DENIED,
      "CONTROL_COMMENTS is not configured; no control comment may be updated."
    );
  }
  const entries = raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (!entries.length || !entries.every((e) => ENTRY_RE.test(e))) {
    throw new ControlError(
      ErrorClass.CONTROL_TARGET_DENIED,
      "CONTROL_COMMENTS is malformed; no control comment may be updated."
    );
  }
  return entries.map((e) => {
    const [, owner, repo, id] = e.match(ENTRY_RE);
    return { owner: owner.toLowerCase(), repo: repo.toLowerCase(), comment_id: Number(id) };
  });
}

export function assertControlComment(env, owner, repo, commentId) {
  const allowed = parseControlComments(env);
  if (!Number.isInteger(commentId)) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "comment_id must be an integer.");
  }
  const hit = allowed.find(
    (c) => c.owner === String(owner).toLowerCase() && c.repo === String(repo).toLowerCase() && c.comment_id === commentId
  );
  if (!hit) {
    throw new ControlError(
      ErrorClass.CONTROL_TARGET_DENIED,
      "That comment is not a configured control comment.",
      { requested: `${owner}/${repo}#${commentId}` }
    );
  }
  return hit;
}
