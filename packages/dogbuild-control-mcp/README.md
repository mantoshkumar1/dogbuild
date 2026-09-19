# `@dogbuild/control-mcp`

DogBuild's dedicated, portable MCP control server.

Owner: [DogBuild #164](https://github.com/mantoshkumar1/dogbuild/issues/164).

Architecture: [DogBuild #170](https://github.com/mantoshkumar1/dogbuild/issues/170).

## Current status

**Implemented for review, not deployed or admitted.** Deployment, Cloudflare
configuration, portal registration, credentials, live canaries and enablement
remain separate founder-authorized actions.

The current server exposes exactly two non-mutating tools:

```text
get_commit_ci
handle_comment_change_request
```

`update_control_comment` is parked and absent from schema, `tools/list`,
dispatch and source handlers. Generic comment editing and deletion are absent.
The previous 38-tool `github-control-worker` is not imported or reachable.

## Why a separate server

The existing GitHub upstreams expose individual Actions reads, but they do not
provide one conservative answer bound to an exact commit across check runs,
workflow runs, jobs and legacy commit statuses. This server keeps that
DogBuild-specific aggregation in one testable place without inheriting generic
GitHub write capabilities. It also gives blank-session agents one deterministic
response when they ask to edit or delete a comment, without granting either
operation.

The package is standalone and dependency-free. It runs as a Cloudflare Worker,
spawns no process and has no browser or founder-laptop fallback.

## `get_commit_ci`

Input:

```json
{
  "owner": "OWNER",
  "repo": "REPOSITORY",
  "sha": "0123456789abcdef0123456789abcdef01234567"
}
```

The SHA must be exactly 40 lowercase hexadecimal characters. Branches,
abbreviated SHAs, PR numbers and “latest” are refused.

Result classes:

| Result | Meaning |
|---|---|
| `SUCCESS` | Evidence exists, every source is complete and every current signal is acceptable. |
| `FAILURE` | Complete evidence contains a blocking failure. |
| `PENDING` | Complete evidence contains work that has not finished. |
| `NO_CHECKS` | Every source was read completely, but no CI evidence exists. Never green. |
| `INCOMPLETE` | Pagination, interpretation or another evidence boundary is incomplete. Never green. |

The aggregate is evidence, not merge or lifecycle authority. It does not move
an issue, PR or Project item, and it does not decide whether a review is done.

### Exact-SHA and completeness rules

1. Verify the commit exists in the allowed repository.
2. Verify every check run and workflow run carries the requested SHA.
3. Follow pagination for check runs, workflow runs, jobs and commit statuses.
4. Use only the newest legacy commit status per case-insensitive context.
5. Include every retrieved current signal in the aggregate.
6. Treat unknown conclusions, malformed evidence, page-cap truncation and
   advertised-total mismatch as `INCOMPLETE`.
7. Bound GitHub requests: at most three pages per collection and ten workflow
   runs' job collections. Crossing a bound reports `INCOMPLETE`; it never
   silently truncates or reports success.
8. Return bounded metadata only. Raw logs and artifact bytes are never read.

GitHub treats `success`, `neutral` and `skipped` check conclusions as successful
status-check outcomes. Cancelled, stale, timed-out, action-required,
startup-failure and failure conclusions are conservatively blocking.

## `handle_comment_change_request`

This tool accepts a structured comment-history intent and returns a policy
decision. It never calls GitHub and never posts, edits or deletes anything.

Supported operations:

| Operation | Result |
|---|---|
| `CORRECTION` | Build `CORRECTION / SUPERSEDES <exact-comment-URL>`. |
| `STATUS_UPDATE` | Build `STATUS UPDATE / REFERENCES <exact-comment-URL>`. |
| `DISPUTE` | Build `DISPUTE / CONTRADICTS <exact-comment-URL>`. |
| `DELETE` + `ORDINARY` | Return `PERMISSION_DENIED` and escalate to Strategy. |
| `DELETE` + `SENSITIVE_EXPOSURE` | Return `FOUNDER_BREAK_GLASS_REQUIRED` without accepting or echoing the sensitive content. |

For the three append operations, the result contains only an
`add_issue_comment` capability name and bounded arguments for the existing
DogBuild GitHub Core MCP server. The calling agent decides whether to make that
separate tool call. This server does not invoke a sibling MCP server and cannot
claim the second call occurred.

Every result explicitly reports:

```text
authorship_verified: false
original_comment_verified: false
authoritative: false
```

Until #167 establishes distinct authenticated agent identities, generated
marker text cannot prove ownership, retract another agent's statement or drive
an automatic lifecycle transition. A future consumer must validate the exact
GitHub record and identities at read time.

Inputs and generated bodies are byte-bounded. Evidence references are bounded,
single-line entries. Delete requests reject append-body fields so accidental
credential/private-data content is not repeated in a result.

## Closed tool surface

`tools/list` has exactly the two entries above and `tools/call` performs an
exact, case-sensitive lookup. Unknown, legacy, parked, generic and destructive
names fail with `UNKNOWN_TOOL` before repository configuration or GitHub
access.

Tests enumerate every legacy name from the current 38-tool package plus parked,
generic and destructive names. Direct invocation proves zero upstream requests.

## Access boundaries

V1 uses three independent checks:

1. exact secret MCP path;
2. independent bearer token;
3. fail-closed `ALLOWED_REPOS` configuration.

The GitHub credential is used only for `GET` requests by `get_commit_ci`;
`handle_comment_change_request` makes no network request. This transport does
not claim to identify Claude, Codex or Strategy. It has no write tool and does
not solve #167. Portal compatibility, real credential scope and Cloudflare
Access must be proven during a later, separately authorized deployment review.

Required configuration:

| Name | Kind | Rule |
|---|---|---|
| `GITHUB_TOKEN` | secret | Read-only credential; scope is independently verified before admission. |
| `MCP_PATH_SECRET` | secret | Exact URL-safe path component for `/mcp/<secret>`; 32–256 characters. |
| `MCP_ACCESS_TOKEN` | secret | Bearer token independent of the path secret; 32–512 URL-safe characters. |
| `ALLOWED_REPOS` | variable | Comma-separated `owner/repository`; unset or malformed denies all tool calls. |

No secret value belongs in `wrangler.toml`, Git, tests, logs or tool results.

## Tests

```sh
cd packages/dogbuild-control-mcp
npm test
```

The tests are offline and dependency-free. They cover:

- the exact two-tool catalogue and real MCP transport;
- path, bearer and configuration denial;
- repository allowlist denial before GitHub access;
- exact commit existence and SHA binding;
- every result class and conclusion mapping;
- pagination for every source, later-page failures and page-cap truncation;
- newest-per-context legacy status selection;
- bounded GitHub requests and bounded returned evidence;
- upstream error classification and credential non-disclosure;
- exhaustive `UNKNOWN_TOOL` rejection with zero upstream requests;
- static absence of parked tools, browser automation and local process spawning;
- runtime proof that `get_commit_ci` issues GitHub `GET` requests only;
- canonical correction, status-update and dispute envelopes;
- ordinary and sensitive-exposure deletion denial;
- zero upstream requests and no authority claims for every comment-change path;
- bounded policy inputs, evidence and generated output;
- absence of edit/update/delete commands in every policy result.

All tests are additive. Existing Python and `github-control-worker` tests are
unchanged and remain part of repository CI.

## Deliberately out of scope

- deployment or portal registration;
- Cloudflare secrets or Access policy;
- agent identity separation (#167);
- posting, editing or deleting comments;
- authoritative correction ownership before #167;
- issue ↔ PR ↔ Project reconciliation;
- branch, file, review, workflow or Project mutation;
- merge or release authority;
- raw logs or artifact download;
- any generic GitHub passthrough.
