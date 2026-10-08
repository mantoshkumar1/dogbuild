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
    name: "get_raw_commit",
    description:
      "Read the exact ordered parents of one 40-character commit SHA and a Merkle-verified recursive " +
      "tree proof, using three read-only requests. COMPLETE is returned only when every step verified; " +
      "anything else is INCOMPLETE or a typed error. The JSON-RPC request must include an id member; " +
      "a request without one is treated as a notification and gets no response.",
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
]);

export function findTool(name) {
  return TOOLS.find((tool) => tool.name === name) || null;
}
