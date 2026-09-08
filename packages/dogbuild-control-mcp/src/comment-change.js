import { ControlError, ErrorClass } from "./errors.js";

export const CommentChangeOperation = Object.freeze({
  CORRECTION: "CORRECTION",
  STATUS_UPDATE: "STATUS_UPDATE",
  DISPUTE: "DISPUTE",
  DELETE: "DELETE",
});

export const DeletionReason = Object.freeze({
  ORDINARY: "ORDINARY",
  SENSITIVE_EXPOSURE: "SENSITIVE_EXPOSURE",
});

export const MAX_CHANGE_TEXT_BYTES = 4_000;
export const MAX_EVIDENCE_REFS = 10;
export const MAX_EVIDENCE_REF_BYTES = 2_048;
export const MAX_GENERATED_BODY_BYTES = 20_000;

const APPEND_FIELDS = ["prior_statement", "new_statement", "evidence_refs", "effect"];

const ENVELOPES = Object.freeze({
  [CommentChangeOperation.CORRECTION]: Object.freeze({
    marker: "CORRECTION / SUPERSEDES",
    priorLabel: "Incorrect prior statement",
    nextLabel: "Correct statement",
    effectLabel: "Effect",
  }),
  [CommentChangeOperation.STATUS_UPDATE]: Object.freeze({
    marker: "STATUS UPDATE / REFERENCES",
    priorLabel: "Previous state",
    nextLabel: "Current state",
    effectLabel: "Effect",
  }),
  [CommentChangeOperation.DISPUTE]: Object.freeze({
    marker: "DISPUTE / CONTRADICTS",
    priorLabel: "Disputed statement",
    nextLabel: "Contrary statement",
    effectLabel: "Interim fail-closed effect",
  }),
});

function byteLength(value) {
  return new TextEncoder().encode(value).length;
}

function positiveInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `${label} must be a positive integer.`);
  }
  return value;
}

function boundedText(value, label, limit = MAX_CHANGE_TEXT_BYTES, { singleLine = false } = {}) {
  if (typeof value !== "string" || !value.trim() || value.includes("\0")) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `${label} must be non-empty bounded text.`);
  }
  const normalized = value.trim();
  if (singleLine && /[\r\n]/.test(normalized)) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `${label} must be one line.`);
  }
  if (byteLength(normalized) > limit) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `${label} exceeds its byte limit.`);
  }
  return normalized;
}

function evidenceRefs(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_EVIDENCE_REFS) {
    throw new ControlError(
      ErrorClass.INVALID_INPUT,
      `evidence_refs must contain between 1 and ${MAX_EVIDENCE_REFS} entries.`
    );
  }
  return value.map((entry, index) => boundedText(
    entry,
    `evidence_refs[${index}]`,
    MAX_EVIDENCE_REF_BYTES,
    { singleLine: true }
  ));
}

function originalUrl(repository, issueNumber, commentId) {
  const owner = encodeURIComponent(repository.owner);
  const repo = encodeURIComponent(repository.repo);
  return `https://github.com/${owner}/${repo}/issues/${issueNumber}#issuecomment-${commentId}`;
}

function verificationBoundary() {
  return {
    authorship_verified: false,
    original_comment_verified: false,
    authoritative: false,
  };
}

function rejectFields(args, fields, operation) {
  const supplied = fields.filter((field) => args[field] !== undefined);
  if (supplied.length) {
    throw new ControlError(
      ErrorClass.INVALID_INPUT,
      `${operation} does not accept fields that could repeat comment content.`,
      { unexpected_fields: supplied.sort() }
    );
  }
}

function handleDelete(repository, args, issueNumber, commentId, url) {
  rejectFields(args, APPEND_FIELDS, CommentChangeOperation.DELETE);
  if (!Object.values(DeletionReason).includes(args.deletion_reason)) {
    throw new ControlError(
      ErrorClass.INVALID_INPUT,
      "deletion_reason must be ORDINARY or SENSITIVE_EXPOSURE."
    );
  }

  const sensitive = args.deletion_reason === DeletionReason.SENSITIVE_EXPOSURE;
  return {
    repository: repository.fullName,
    issue_number: issueNumber,
    original_comment_id: commentId,
    original_comment_url: url,
    operation: CommentChangeOperation.DELETE,
    decision: sensitive ? "FOUNDER_BREAK_GLASS_REQUIRED" : "PERMISSION_DENIED",
    policy: "AI_COMMENT_HISTORY_APPEND_ONLY",
    ...verificationBoundary(),
    github_command: null,
    escalation: {
      target: sensitive ? "FOUNDER" : "STRATEGY",
      action: sensitive
        ? "Stop. Do not repeat the sensitive material. Request founder-only removal."
        : "Do not delete history. Ask Strategy whether an append-only clarification is required.",
    },
  };
}

function handleAppend(repository, args, issueNumber, commentId, url) {
  if (args.deletion_reason !== undefined) {
    throw new ControlError(ErrorClass.INVALID_INPUT, `${args.operation} does not accept deletion_reason.`);
  }
  const envelope = ENVELOPES[args.operation];
  if (!envelope) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "operation is not recognized.");
  }

  const prior = boundedText(args.prior_statement, "prior_statement");
  const next = boundedText(args.new_statement, "new_statement");
  const evidence = evidenceRefs(args.evidence_refs);
  const effect = boundedText(args.effect, "effect");
  const body = [
    `${envelope.marker} ${url}`,
    `${envelope.priorLabel}:\n${prior}`,
    `${envelope.nextLabel}:\n${next}`,
    `Evidence:\n${evidence.map((entry) => `- ${entry}`).join("\n")}`,
    `${envelope.effectLabel}:\n${effect}`,
  ].join("\n\n");

  if (byteLength(body) > MAX_GENERATED_BODY_BYTES) {
    throw new ControlError(ErrorClass.INVALID_INPUT, "Generated comment exceeds its byte limit.");
  }

  return {
    repository: repository.fullName,
    issue_number: issueNumber,
    original_comment_id: commentId,
    original_comment_url: url,
    operation: args.operation,
    decision: "APPEND_COMMENT",
    policy: "AI_COMMENT_HISTORY_APPEND_ONLY",
    ...verificationBoundary(),
    github_command: {
      capability: "add_issue_comment",
      preferred_tool: "dogbuild-github-core_add_issue_comment",
      arguments: {
        owner: repository.owner,
        repo: repository.repo,
        issue_number: issueNumber,
        body,
      },
    },
  };
}

export function handleCommentChangeRequest(repository, args) {
  const issueNumber = positiveInteger(args.issue_number, "issue_number");
  const commentId = positiveInteger(args.original_comment_id, "original_comment_id");
  const url = originalUrl(repository, issueNumber, commentId);

  if (args.operation === CommentChangeOperation.DELETE) {
    return handleDelete(repository, args, issueNumber, commentId, url);
  }
  return handleAppend(repository, args, issueNumber, commentId, url);
}
