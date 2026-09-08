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
]);

export function findTool(name) {
  return TOOLS.find((tool) => tool.name === name) || null;
}
