const repositoryProperties = {
  owner: { type: "string", minLength: 1, maxLength: 100, description: "GitHub repository owner" },
  repo: { type: "string", minLength: 1, maxLength: 100, description: "GitHub repository name" },
};

export const TOOLS = Object.freeze([
  Object.freeze({
    name: "get_commit_ci",
    description:
      "Read a conservative CI aggregate for one exact 40-character commit SHA. " +
      "No checks or incomplete evidence is never reported as success.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...repositoryProperties,
        sha: {
          type: "string",
          pattern: "^[0-9a-f]{40}$",
          description: "Exact lowercase 40-character commit SHA",
        },
      },
      required: ["owner", "repo", "sha"],
    },
  }),
  Object.freeze({
    name: "handle_comment_change_request",
    description:
      "Use whenever an agent wants to edit, update, correct, dispute, or delete a GitHub comment. " +
      "This policy-only tool never mutates GitHub: it returns an append-only add-comment command " +
      "or a Strategy/founder escalation decision.",
    inputSchema: {
      type: "object",
      additionalProperties: false,
      properties: {
        ...repositoryProperties,
        issue_number: { type: "integer", minimum: 1, description: "Issue or PR conversation number" },
        original_comment_id: { type: "integer", minimum: 1, description: "Referenced issue-comment id" },
        operation: {
          type: "string",
          enum: ["CORRECTION", "STATUS_UPDATE", "DISPUTE", "DELETE"],
          description: "Structured reason for requesting a comment-history change",
        },
        prior_statement: { type: "string", description: "Prior, previous, or disputed statement" },
        new_statement: { type: "string", description: "Correct, current, or contrary statement" },
        evidence_refs: {
          type: "array",
          minItems: 1,
          maxItems: 10,
          items: { type: "string", minLength: 1, maxLength: 2048 },
        },
        effect: { type: "string", description: "Effect or interim fail-closed consequence" },
        deletion_reason: {
          type: "string",
          enum: ["ORDINARY", "SENSITIVE_EXPOSURE"],
          description: "Required only for DELETE; never include the sensitive content itself",
        },
      },
      required: ["owner", "repo", "issue_number", "original_comment_id", "operation"],
    },
  }),
]);

export function findTool(name) {
  return TOOLS.find((tool) => tool.name === name) || null;
}
