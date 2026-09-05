# `@dogbuild/github-control-worker`

Browser-free GitHub control adapter for scheduled DogBuild agents.
Owner: [dogbuild#164](https://github.com/mantoshkumar1/dogbuild/issues/164).

## Why this exists

Scheduled agents needed two GitHub operations the available connector did not
expose: editing one existing issue comment in place, and reading the CI verdict
for an exact commit. Lacking both, an agent fell back to driving a GUI browser.
That fallback is what this package removes — not by working around the gap, but
by providing the operations as structured, fail-closed tools.

Execution is remote (Cloudflare Workers). There is no local process, no
`npm exec` child, no Docker, and no browser, so a scheduled session that ends
leaves nothing behind to reap.

> **Hosted-adapter exception.** DogBuild's general rule is local-first with no
> hosted backend. This package is a deliberate, narrow exception approved on
> #164: it is a remote adapter *because* a per-session local server was the
> cause of the process accumulation it replaces. The exception covers this
> package only and does not relax DogBuild's local-first rules anywhere else.

## Capability profiles

Authority comes from the `profiles` field on each tool. `tools/list` returns
only the caller's profile and `tools/call` re-checks before dispatch, so a tool
outside your profile is unreachable, not merely undocumented.

| Profile | Gets |
|---|---|
| `read` | All common reads: issues and comments; exact PR state, base/head SHAs, files, commit lineage, reviews, review threads; bounded file reads; `get_commit_ci`; workflow jobs and artifact metadata; Projects-v2 readback. |
| `implementor` | Common reads, plus issue/PR metadata create-update, bounded comments, labels, assignees, task-branch creation and file writes, PR open/update, Projects-v2 field updates. |
| `reviewer` | Common reads, plus one exact-head `COMMENT` review, one terminal handoff comment, and in-place status-comment update with optimistic concurrency. |

Claude and Codex have identical *capabilities*; DogBuild grants the *authority*
for one task by signing one role assertion. Capability symmetry is not
simultaneous authority.

## Role enforcement

The role is resolved from the `x-dogbuild-role-assertion` request header only.
Tool arguments are never consulted, so a caller cannot name or widen its own
role. The assertion is an HMAC-SHA256 token minted by DogBuild binding role,
task, repository, optional branch, subject, optional producer, nonce and
expiry. A reviewer assertion whose `producer` equals its `subject` is rejected:
a producer cannot hold independent-review authority over its own lineage.

**No assertion means read-only.** An unsigned request gets common reads and
nothing else. If `ROLE_ASSERTION_KEY` is unset, no role can be granted at all.

### Write-target scoping

A valid signature proves who issued the assertion, not what it permits.
Every write is therefore additionally bound to a target the assertion names,
and the check runs **before any upstream request is issued**:

| Assertion field | Governs |
|---|---|
| `issues: [n, …]` | `update_issue`, `add_issue_comment`, `add_labels`, `remove_label`, `add_assignees`, `remove_assignees` |
| `comments: [id, …]` | `update_issue_comment` |
| `pull_requests: [n, …]` | `update_pull_request`, `publish_review` |
| `projects: [n, …]` | `add_project_item`, `update_project_item_field` |
| `branch: "…"` | `create_branch`, `create_or_update_file`, and the `head` of `create_pull_request` |
| `allow_create_issue: true` | `create_issue` |

Fail-closed by construction: an assertion that declares no list for a kind of
object authorizes **no** write of that kind. Reads are unaffected — scoping
governs writes, not visibility.

### Known limits, stated plainly

- The Worker validates that an assertion is well-formed, unexpired, bound to
  the requested repository and target, and not self-review. It cannot validate
  DogBuild's wider lineage predicates — role locks after meaningful lineage
  start, control generation, duplicate-effect prevention — because it holds no
  lineage state. Those belong to the DogBuild-side issuer and auto-merger.
- Nonces are carried and bound but not yet replay-checked server-side; the
  replay window is bounded only by the one-hour maximum lifetime.
- `subject` is bound into the signature but cannot be independently verified
  server-side: the Worker has no channel-level caller identity. Issuing the
  right subject is the DogBuild issuer's responsibility.
- The OAuth layer is ported unchanged from the reference Worker and is *not*
  the access control (`/mcp/<MCP_PATH_SECRET>` is). Strategy accepted it as
  existing state. Real client validation, short-lived access tokens and replay
  protection remain follow-up work.

## Server invariants

1. **Hard repository allowlist.** `ALLOWED_REPOS` unset or malformed denies
   everything. There is no "unset means unrestricted" path.
2. **Exact SHA validation and binding.** 40 lowercase hex characters, and every
   returned record is verified to belong to that SHA or the call fails closed.
3. **Complete pagination or explicit `incomplete: true`.** Never a silent truncation.
4. **One normalized CI verdict:** `pending | success | failure | neutral | unknown`,
   folded from **every** retrieved signal — check-runs, legacy commit statuses,
   workflow runs per attempt, and their jobs. `evidence_breakdown` reports the
   count from each source, so retrieved-but-uncounted evidence is visible.
5. **Comment updates** use `expected_updated_at`, bounded body size, stable
   comment id, and a returned `body_sha256`.
6. **Exact-head re-read** immediately before publishing a review; a moved head rejects.
7. **Deterministic error classes** for timeout, rate limit, 401, 403, 404, 409,
   422 and malformed upstream responses.
8. **Logs and artifacts are metadata-only.** No raw download until a separately
   reviewed, bounded, redacting reader exists.
9. **Absent by construction:** merge, auto-merge, ref or branch delete, file
   delete, comment delete, issue/PR close or reopen, workflow
   dispatch/rerun/cancel, check or status mutation, review dismissal,
   approval-as-finalization, secrets, variables, webhooks, environments,
   deployments, administration, branch-protection mutation, and any general API
   passthrough. Writes to `main`, `master`, `staging` and `production` are
   refused in every profile.
10. **Credential isolation.** `PROJECT_TOKEN`, if set, is used only by
    Projects-v2 handlers and never by general GitHub operations.

`get_commit_ci` is deliberately conservative: absent, incomplete, ambiguous or
head-mismatched evidence resolves to `unknown`. It will never report green by
absence, and it will never report green while any retrieved run or job failed —
reporting a false green would be a worse failure than the browser dependency
this package removes.

## Configuration

See `wrangler.toml.example`. Secrets are set with `wrangler secret put` and
never committed. `ALLOWED_REPOS` and `ROLE_ASSERTION_KEY` are required for any
write path to function.

## Tests

```sh
cd packages/github-control-worker && npm test
```

Fully offline: `fetch` is mocked, no network, no credentials, no browser. The
suite covers allowlist denial before any request, SHA validation and binding,
pagination completeness and truncation, the never-green-by-absence rule, the
full normalization vocabulary, failed workflow runs and jobs dominating passing
check-runs, stale-version refusal before any write, comment idempotency, the
error-class taxonomy, role forgery/expiry/replay/self-review rejection,
argument-supplied roles being ignored, write-target scope denial with zero
upstream requests, profile isolation, and static proof that no source file
references a browser or spawns a process.

## Status

Not deployed. The existing Worker is unchanged. Deployment, connector cutover,
credential provisioning and live conformance are founder-controlled and happen
only after independent review on #164.
