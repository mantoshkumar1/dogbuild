# Two-Week MVP Scope

## In scope (Lite)
A deterministic, local, file-based CLI implementing one canonical protocol:

1. **Canonical project-state schema** — the single source of truth on disk.
2. **Deterministic local CLI** — the command surface; same input → same output.
3. **State initialization & checkpointing** — create/update verified state.
4. **Evidence-backed status reconstruction** — rebuild "where are we" from git
   (branch/commit/dirty) + the state file, with evidence, not narration.
5. **Agent handoff generation** — a structured packet an execution agent hands to
   the next one.
6. **ChatGPT Web review-request generation** — a packet the human uploads to
   ChatGPT (manual file exchange).
7. **Structured review-decision import** — parse ChatGPT's structured decision
   back in.
8. **Stale-decision & repository-identity validation** — reject decisions whose
   repo/branch/commit no longer match.
9. **Deterministic authority gate** — APPROVE / APPROVE_WITH_CONDITIONS / VETO /
   NEEDS_HUMAN, enforced by rules, not judgment.
10. **Thin Claude / Cursor / Codex adapters** — over the one canonical protocol.
11. **Dogfooding** — in PhotoSahi and in Project State Keeper itself.

## Out of scope (hard boundaries — do not add)
- ❌ OpenAI API / any automated ChatGPT call
- ❌ browser automation
- ❌ hosted backend
- ❌ user accounts
- ❌ payment system
- ❌ dashboard / GUI
- ❌ cloud sync
- ❌ multi-repo / team / shared state
- ❌ four separate implementations — **one canonical protocol, thin adapters only**

## Principles
- **Local-only, file-based, deterministic.** The gate's decision must be
  reproducible and inspectable.
- **Verification over trust.** Every decision is checked against real repo
  identity/branch/commit and freshness before it can unlock execution.
- **Human authority is supreme.** No irreversible action is ever auto-performed
  (see [`authority-model.md`](authority-model.md)).
- **The human never reconstructs context by hand** — that is the whole point.
