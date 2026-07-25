# Project State (current)

> Generated from `.ai/state.json`. Current facts only; history lives in `.ai/events.jsonl` and the Checkpoints section below.

- **Schema version:** 1.0.0
- **PSK id:** `e29a3a07-7a2c-4f9d-a44c-127e30fd89be`
- **Repo root:** `/Users/mantoshkumar/Desktop/project/project-state-keeper`
- **State updated:** 2026-07-25T20:47:15Z

## Objective

(v1, set 2026-07-25T18:26:36Z)

Build Project State Keeper MVP (dogfood-first). Day 1: canonical project-state schema.

## Active scope

(v4, set 2026-07-25T20:45:53Z)

Day 4: Orientation Brief + generic handoff slice

## Git state (as last captured)

- **Branch:** `main`
- **HEAD:** `019f519bdc8b2fced7bf2e7197d7b62e028180d1`
- **Worktree:** dirty (fingerprint `c290a8eaf7c1…`)
- **Captured:** 2026-07-25T20:47:15Z

## Requested items

- **[done]** Day 4 dogfood: Claude->Claude handoff for where-am-i alias test + doc example (`3d9cf933-3272-4df8-b0b9-7f6bf4f894d0`, updated 2026-07-25T20:47:14Z)
- **[done]** Day 2: CLI skeleton, exit codes, identity, registry, context commands (`867b4e2d-30bc-4b71-922f-3ef4511626dd`, updated 2026-07-25T19:53:41Z)
- **[done]** Day 1: canonical project-state schema + store + projection + tests (`98dc8aff-6f86-40f8-8d8a-aa1ed99c77f2`, updated 2026-07-25T18:26:36Z)
- **[done]** Day 3: first end-to-end review acceptance (real ChatGPT APPROVE) (`d15877ab-2e32-49a9-83af-4d741a66fc73`, updated 2026-07-25T20:27:14Z)

## Reserved human-only approvals

- delete_data
- deploy
- external_comm
- merge
- publish
- push
- scope_change
- secrets_or_prod
- spend

## Decisions (records)

- **APPROVE** by human on `commit Day 1 implementation` (commit `a84e2d1e`, `5799509e-b4fb-4761-a06b-ce8c5db217a2`)
- **APPROVE** by chatgpt on `Add a new file docs/example-review-workflow.md containing a concise, documented example of the completed manual ChatGPT review workflow (request -> upload -> decision -> import -> gate -> action -> checkpoint). Documentation only; no code changes; fully reversible.` (commit `e8986fe7`, `bd3d8db4-1150-4cd8-871f-2406a0e989f4`)
- **APPROVE** by human on `commit Day 2 implementation` (commit `a84e2d1e`, `c53d8fc6-d8ac-4ece-8240-8bab72b19eac`)

## Checkpoints (historical claims)

### 2026-07-25T18:26:36Z — Day 1 complete: canonical schema, store, models, projection, 26 tests green

- Implemented:
  - .ai/ dir model: state.json + events.jsonl + STATE.md
  - repo identity (persistent UUID), git state + dirty fingerprint, sanitized remotes
  - versioned objective/scope, item status model, evidence + decision records, reserved approvals, checkpoints
  - JSON schemas, typed models, validation, atomic safe-init serialization, deterministic Markdown projection
- Next safe action: Day 2: deterministic local CLI skeleton (subcommands, exit codes) over the core API
- Unresolved risks:
  - PAYMENT + DISTRIBUTION unvalidated (dogfood-first; recorded in revenue-opportunity-lab)
  - legacy-Markdown importer not built; authority gate is Day 10

### 2026-07-25T19:53:41Z — Day 2 complete: deterministic CLI + Project Context Resolver, 38 tests green

- Implemented:
  - CLI (statekeeper==python -m psk): subcommands, stable exit codes, human+JSON output
  - persistent .ai/PROJECT_IDENTITY.json (stable UUIDs, survives moves, remote as hash fingerprint only)
  - local registry ~/.project-state-keeper/projects.json (env-overridable; no code/secrets)
  - context identify/show/list/register/export --for chatgpt; choose/verify reserved
  - resolution outcomes + evidence-priority spec; ChatGPT CONTEXT_INSTRUCTIONS; .ai excluded from dirty/stale
- Next safe action: Day 3: agent handoff generation (statekeeper handoff) carrying project_id/repository_id + current state, building on the identity/packet-header work
- Unresolved risks:
  - PAYMENT + DISTRIBUTION unvalidated (dogfood-first)
  - AMBIGUOUS/STALE/MISMATCH import-time resolution not built yet (Day 3+); choose/verify reserved
  - ChatGPT Web cannot inspect tabs/repos — manual packet upload only

### 2026-07-25T20:27:15Z — Day 3 acceptance COMPLETE: real ChatGPT APPROVE imported, gate PROCEED, approved doc added

- Implemented:
  - review request -> real ChatGPT decision -> import (validated) -> gate PROCEED -> approved action -> checkpoint
  - decision archived unchanged under .ai/exchange/archive/<packet-id>/
  - approved action performed: docs/example-review-workflow.md (documentation only, reversible)
- Next safe action: Next slice: versioned reviewer policy + full outcomes (VETO/APPROVE_WITH_CONDITIONS/NEEDS_HUMAN) + one evidence-based revision loop; then Orientation Brief; then Claude->Codex handoff
- Unresolved risks:
  - manual courier transport is a temporary proof mechanism, not the product experience (validated problem)
  - founder-orientation-loss: state is machine-readable but not human-glanceable (validated problem)
  - PAYMENT + DISTRIBUTION still unvalidated

### 2026-07-25T20:47:15Z — Day 4 complete: Orientation Brief + generic handoff; real Claude->Claude handoff dogfood

- Implemented:
  - Orientation Brief (brief/where-am-i + --json) with truth-order conflict display
  - working-agent declaration; operating mode; generic agent handoff (claude/codex) create/show/consume
  - single-agent dogfood: declaration -> handoff create -> consume(validate identity/branch/HEAD/scope/freshness) -> delegated task -> tests -> checkpoint
  - delegated task performed: human-readable where-am-i alias CLI test + doc example
- Next safe action: Versioned reviewer-policy slice: policy id+version+hash in request/decision, machine-evidence vs agent-claim separation, VETO/APPROVE_WITH_CONDITIONS/NEEDS_HUMAN, one evidence-based revision loop
- Unresolved risks:
  - cross-model execution with Codex UNTESTED (Codex unavailable) — Codex handoff generation is tested, execution is not
  - manual transport still required for ChatGPT reviews (automation not built)
  - PAYMENT + DISTRIBUTION unvalidated

