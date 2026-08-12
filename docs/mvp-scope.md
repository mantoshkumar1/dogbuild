# Historical Two-Week MVP Scope

> **Historical foundation, superseded as the active product boundary.** This
> two-week local-only scope was completed as DogBuild's first proof. The current
> direction is the founder-first remote-control MVP documented in `vision.md`
> and sequenced in `next-slices.md`. This file remains to preserve the original
> constraints and prevent retrospective claims that its automation already
> existed.

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
11. **Dogfooding** — in PhotoSahi and in DogBuild itself.

## Out of scope for the historical two-week MVP
- ❌ OpenAI API / any automated ChatGPT call
- ❌ browser automation
- ❌ hosted backend
- ❌ user accounts
- ❌ payment system
- ❌ dashboard / GUI
- ❌ cloud sync
- ❌ multi-repo / team / shared state
- ❌ four separate implementations — **one canonical protocol, thin adapters only**

The current remote-control direction retains the no-hosted-backend, no-dashboard,
no-payment, no-cloud-sync, and single-protocol constraints. It intentionally
revisits only the former blanket exclusion of automation: GitHub is the planned
asynchronous transport between a remote planning surface and a local runtime,
without exposing the local machine to inbound internet traffic.

## Principles
- **Local-only, file-based, deterministic.** The gate's decision must be
  reproducible and inspectable.
- **Verification over trust.** Every decision is checked against real repo
  identity/branch/commit and freshness before it can unlock execution.
- **Human authority is supreme.** No irreversible action is ever auto-performed
  (see [`authority-model.md`](authority-model.md)).
- **The human never reconstructs context by hand** — that is the whole point.
