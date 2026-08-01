# Project Context Resolver

Answers one question: **which project and repository does this request, chat,
packet, decision, or handoff belong to?** State Keeper answers *"what is the truth
of this repo?"*; the Context Resolver answers *"which repo is this conversation
about?"* Both are required.

Local agents (Claude/Cursor/Codex) can identify the repository automatically from
the working directory. **ChatGPT Web cannot inspect your Mac or browser tabs**, so
the two-week MVP uses **explicit project identities and mismatch detection**, not
pretended automation.

## Identity model
Every initialized repository has a persistent identity file:
```
.ai/PROJECT_IDENTITY.json
```
```json
{
  "schema_version": 1,
  "project_id": "persistent-uuid",
  "display_name": "DogBuild",
  "repository_id": "persistent-repository-uuid",
  "repository_name": "dogbuild",
  "root_path": "/current/local/path",
  "remote_fingerprint": null,
  "aliases": ["PSK", "statekeeper", "project state keeper"],
  "parent_system": {
    "name": "Optional upstream product system",
    "record": "https://example.test/versioned-product-record"
  },
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```
Requirements:
- `project_id` and `repository_id` are **stable UUIDs**.
- Absolute paths are **informational, not identity** (identity survives moves).
- **Authenticated remote URLs must never be stored** — only a `remote_fingerprint`
  (a hash of the sanitized remote), or `null`.
- Aliases are explicit and editable.
- `parent_system` is optional, explicit source metadata. Ordinary repositories
  do not inherit DogBuild's own product-incubation source.
- Every checkpoint, handoff, review request, and review decision **must carry the
  project and repository IDs.**

## Local project registry (outside individual repos)
```
~/.project-state-keeper/projects.json
```
May contain: project id, repository id, display name, current local path, aliases,
remote fingerprint, last-seen branch/HEAD, last-used timestamp, parent record.
**No source code, secrets, or conversation content.** Local-only; **not required**
for portable repository state (the repo's own `.ai/` is authoritative).

## Resolution outcomes (deterministic)
```
IDENTIFIED  one project supported by strong evidence
AMBIGUOUS   two or more projects remain plausible -> STOP, ask one focused question
UNKNOWN     insufficient evidence to associate with any known project
STALE       known project, but obsolete branch/commit/scope/snapshot
MISMATCH    imported decision/handoff claims a different repo/project than local
```
**No execution may proceed under `AMBIGUOUS`, `UNKNOWN`, `STALE`, or `MISMATCH`.**

## Evidence priority (highest first)
1. Explicit project & repository IDs in a valid PSK packet.
2. Explicit project ID supplied by the user.
3. Current local working directory (Claude/Cursor/Codex).
4. Repository metadata and `.ai/PROJECT_IDENTITY.json`.
5. Explicit repository name/path/remote/commit supplied in the request.
6. Explicit aliases from the local registry.
7. Recent project usage.
8. Semantic inference from conversation content.

**Semantic inference alone must never authorize repository changes.** When only
semantic evidence exists, return `AMBIGUOUS` or `UNKNOWN`.

## CLI commands (added or reserved)
```bash
statekeeper context identify          # local agent: identify repo from cwd + git
statekeeper context show              # print a concise context card
statekeeper context list              # known local projects (no secrets)
statekeeper context register          # ensure identity + add/update registry
statekeeper context choose <id>       # (reserved) pick among plausible projects
statekeeper context export --for chatgpt   # write an uploadable context packet
statekeeper context verify <file>     # (reserved) verify an imported context/decision
```
`statekeeper` is the installed entry point; `python -m psk` is equivalent.

`context show` prints:
```
Project: DogBuild
Project ID: <uuid>
Repository: dogbuild
Branch: main
HEAD: <sha>
Scope: Day 2 CLI skeleton
State freshness: current
```

`context export --for chatgpt` generates:
```
.ai/exchange/outbox/<packet-id>-chat-context.md
```
including: project id, repository id, project name, repository name, branch, HEAD,
dirty-worktree fingerprint (when applicable), active scope, current objective,
current state summary, exact purpose of the ChatGPT conversation, timestamp, and
freshness rules. **Safe to upload without the repository contents.**

## Chat-context continuity — packet header
Every generated ChatGPT review packet must include a visible header:
```yaml
project_id: <uuid>
repository_id: <uuid>
project_name: DogBuild
repository_name: dogbuild
branch: main
head: <full-sha>
scope_id: <uuid>
scope_revision: 1
packet_created_at: <timestamp>
```
Every ChatGPT decision must return those identifiers. **Import must reject:** wrong
project id, wrong repository id, wrong branch, stale HEAD, stale dirty fingerprint,
wrong scope revision, or a decision copied from another chat/project. This protects
the user even when a response is copied from the wrong browser window.

## Human experience
```
ChatGPT chat:                          Local agent:
  open/return to a chat                  agent starts inside repository
  → upload one context/review packet     → PSK identifies local project automatically
  → ChatGPT identifies the exact project → agent reads current state + scope
  → reviews only that project state      → no user explanation required
  → decision carries the same identity
  → local import rejects wrong/stale decisions
```

## Later product possibilities (recorded, NOT implemented; not in MVP)
Browser extension labeling ChatGPT tabs by project; automatic upload/download
relay; ChatGPT API integration; desktop tray app; auto-opening the correct
ChatGPT conversation; browser-window/conversation discovery; cross-chat search.
These need browser/API integration. **Do not claim automatic browser routing until
it exists.**
