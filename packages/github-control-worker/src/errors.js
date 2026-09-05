/**
 * Deterministic error taxonomy (DogBuild #164 invariant 7).
 *
 * Every failure leaving this package carries one stable `class` string so a
 * caller can branch on it mechanically instead of parsing prose. No error
 * message ever contains a token, an Authorization header, an OAuth value, a
 * path secret, or a request/response body.
 */

export const ErrorClass = {
  ALLOWLIST_DENIED: "ALLOWLIST_DENIED",
  CONFIG_INVALID: "CONFIG_INVALID",
  INVALID_INPUT: "INVALID_INPUT",
  ROLE_DENIED: "ROLE_DENIED",
  SELF_REVIEW_DENIED: "SELF_REVIEW_DENIED",
  BRANCH_DENIED: "BRANCH_DENIED",
  STALE_VERSION: "STALE_VERSION",
  HEAD_MISMATCH: "HEAD_MISMATCH",
  INCOMPLETE_EVIDENCE: "INCOMPLETE_EVIDENCE",
  UNAUTHORIZED: "UNAUTHORIZED",
  FORBIDDEN: "FORBIDDEN",
  NOT_FOUND: "NOT_FOUND",
  CONFLICT: "CONFLICT",
  UNPROCESSABLE: "UNPROCESSABLE",
  RATE_LIMIT: "RATE_LIMIT",
  TIMEOUT: "TIMEOUT",
  UPSTREAM_MALFORMED: "UPSTREAM_MALFORMED",
  UPSTREAM_ERROR: "UPSTREAM_ERROR",
  UNKNOWN_TOOL: "UNKNOWN_TOOL",
};

export class ControlError extends Error {
  constructor(errorClass, message, details = {}) {
    super(message);
    this.name = "ControlError";
    this.class = errorClass;
    this.details = details;
  }
  toJSON() {
    return { error_class: this.class, message: this.message, ...this.details };
  }
}

/** Map an upstream HTTP status onto exactly one error class. */
export function classifyHttpStatus(status, headers) {
  const remaining = headers && typeof headers.get === "function" ? headers.get("x-ratelimit-remaining") : null;
  if (status === 401) return ErrorClass.UNAUTHORIZED;
  if (status === 403) return remaining === "0" ? ErrorClass.RATE_LIMIT : ErrorClass.FORBIDDEN;
  if (status === 404) return ErrorClass.NOT_FOUND;
  if (status === 409) return ErrorClass.CONFLICT;
  if (status === 422) return ErrorClass.UNPROCESSABLE;
  if (status === 429) return ErrorClass.RATE_LIMIT;
  return ErrorClass.UPSTREAM_ERROR;
}
