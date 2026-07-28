# Project State (current)

> Generated from `.ai/state.json`. Current facts only; history lives in `.ai/events.jsonl` and the Checkpoints section below.

- **Schema version:** 1.0.0
- **PSK id:** `e29a3a07-7a2c-4f9d-a44c-127e30fd89be`
- **Repo root:** `/Users/mantoshkumar/Desktop/project/project-state-keeper`
- **State updated:** 2026-07-28T03:57:14Z

## Objective

(v1, set 2026-07-25T18:26:36Z)

Build Project State Keeper MVP (dogfood-first). Day 1: canonical project-state schema.

## Active scope

(v8, set 2026-07-28T03:56:54Z)

Real use over several normal work sessions, then one outside-user installation test. The local control loop milestone (revision 1) is COMPLETE, proven end to end on PhotoSahi and closed on 2026-07-27.

## Git state (as last captured)

- **Branch:** `main`
- **HEAD:** `b985dfb81f952ad6b1e5239425314af5fc8a9fc7`
- **Worktree:** clean
- **Captured:** 2026-07-28T03:57:14Z

## Requested items

- **[done]** Day 4 dogfood: Claude->Claude handoff for where-am-i alias test + doc example (`3d9cf933-3272-4df8-b0b9-7f6bf4f894d0`, updated 2026-07-25T20:47:14Z)
- **[done]** Day 6: reviewer policy + full exception handling (`4848efa1-c769-4a1d-8932-bc90328b4aae`, updated 2026-07-25T21:59:52Z)
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

- **APPROVE** by chatgpt on `Commit the reviewer-policy slice (implementation + tests)` (commit `e50fe959`, `0410e3fd-c97a-4a35-ae72-8279c6dad9b7`)
- **APPROVE_WITH_CONDITIONS** by chatgpt on `Doc with conditions` (commit `e50fe959`, `1ee0066e-4e1c-4954-9c86-b6900d3f294f`)
- **VETO** by chatgpt on `Risky change` (commit `e50fe959`, `36843386-2b42-47a1-b4eb-283aa95cd473`)
- **APPROVE** by human on `commit Day 1 implementation` (commit `a84e2d1e`, `5799509e-b4fb-4761-a06b-ce8c5db217a2`)
- **VETO** by chatgpt on `Risky change` (commit `e50fe959`, `62fa803f-6c6d-42ad-af1c-03d17327b6ae`)
- **NEEDS_HUMAN** by chatgpt on `Add silent paid API calls now` (commit `e50fe959`, `64c47209-9030-486a-961b-d5e9c708749d`)
- **APPROVE** by chatgpt on `Add a doc` (commit `e50fe959`, `b73f9f7c-0fab-487a-80c5-00e70f54770c`)
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

### 2026-07-25T21:06:33Z — Project Genesis and Goal Lock

- Implemented:
  - genesis import + goal contract
  - idea parking lot
  - goal-drift alignment
  - goal-driven Orientation Brief; warnings != human interruption
- Next safe action: the next agreed implementation slice: versioned reviewer policy (VETO/APPROVE_WITH_CONDITIONS/NEEDS_HUMAN + evidence-based revision loop)
- Unresolved risks:
  - Codex execution untested
  - full reviewer policy reserved
  - PAYMENT/DISTRIBUTION unvalidated

### 2026-07-25T21:59:52Z — Day 6 complete: versioned reviewer policy + full gate outcomes + veto revision + human loop

- Implemented:
  - versioned reviewer policy (show/verify, deterministic fingerprint)
  - policy+goal bindings on requests/decisions; reject missing/mismatched/stale/unknown
  - APPROVE/APPROVE_WITH_CONDITIONS/VETO/NEEDS_HUMAN outcomes; conditions tracked
  - one new-evidence veto revision; second revision rejected
  - human show/decide + resume verify; brief blocker-vs-warning; monotonic seq determinism
- Next safe action: Next slice (recommend): package a first usable end-to-end walkthrough OR add the founder-policy enforcement fields to the Goal Contract (small governance-data sync)
- Unresolved risks:
  - Codex cross-model execution untested
  - transport still manual
  - PAYMENT/DISTRIBUTION unvalidated

### 2026-07-25T22:21:44Z — Recovery reconcile: canonical state refreshed to live HEAD 60b5249 (previous Claude window lost); no product code changed

- Implemented:
  - refreshed canonical git_state to live HEAD 60b5249d
  - recorded recovery reconciliation checkpoint
  - excluded untracked case-study PDF via .git/info/exclude (local-only)
- Next safe action: Phase 2: first visible end-to-end user walkthrough in a disposable repo (install -> init -> genesis -> review gate -> approved README -> checkpoint)
- Unresolved risks:
  - PAYMENT/DISTRIBUTION unvalidated
  - Codex cross-model execution untested
  - manual reviewer transport still required

### 2026-07-25T22:33:27Z — First visible user run proven end-to-end; review-request CLI crash fixed; canonical state reconciled

- Implemented:
  - fixed review-request CLI crash (evidence->machine_evidence) + CLI regression test
  - docs/first-run-walkthrough.md quickstart
  - reconciled canonical state to HEAD and excluded case-study PDF locally (.git/info/exclude)
- Next safe action: Commit .ai dogfood state; optionally sync Revenue Opportunity Lab; then choose the next milestone slice
- Unresolved risks:
  - real cross-provider reviewer transport still manual
  - Codex cross-model execution untested
  - PAYMENT/DISTRIBUTION unvalidated

### 2026-07-25T23:30:33Z — Personal alpha packaged: dogbuild command + canonical Claude skill + offline installer; 97 tests green

- Implemented:
  - dogbuild console-script alias (statekeeper/psk unchanged; no rename)
  - offline idempotent dogbuild install claude (psk/install.py) with --dry-run
  - canonical bundled skill psk/skills/dogbuild/SKILL.md
  - docs/personal-alpha.md (technical vs human view)
  - tests/test_install_and_skill.py (8 tests)
- Next safe action: Fresh-session acceptance test in PhotoSahi (What's happening?); do not begin the next milestone
- Unresolved risks:
  - external demand / payment / distribution unvalidated
  - founder real macOS ~/.claude not reachable from this VM (skill delivered as file + install command)

### 2026-07-26T01:07:22Z — Owner-away autonomy + pending owner-input reconciliation shipped; 114 tests green

- Implemented:
  - psk/autonomy.py: human-approved Autonomy Contract + lifecycle + instruction epoch
  - owner-input queue with 6-way classification + reconciliation (per-message outcomes)
  - in-flight race protection via instruction epoch on review requests
  - continuation packet + owner-return brief + self-repair limit + goal-change confirmation phrase
  - CLI: dogbuild autonomy/input/continuation (statekeeper aliases preserved)
  - canonical Claude skill updated with the autonomy/reconciliation rules
- Next safe action: Owner runs the fresh-session/owner-return usage; do not begin the next slice
- Unresolved risks:
  - external demand / payment / distribution unvalidated
  - automatic cross-provider transport deferred (manual structured protocol)

### 2026-07-26T16:53:31Z — Claude hook-settings fix shipped: dogbuild start now writes valid PreToolUse matcher groups; 279 tests green

- Implemented:
  - build_hooks_config emits matcher-group -> nested hooks-array structure
  - merge_hooks_config preserves unrelated settings, hook events, and PreToolUse groups
  - DogBuild's own hook identified by psk.governor.broker marker and replaced in place (idempotent)
  - legacy flat DogBuild hook entries repaired rather than left behind
- Next safe action: Owner confirms dogbuild start in a real terminal; do not begin the next slice
- Unresolved risks:
  - Interactive TUI startup verified headlessly (no TTY available to the agent); owner should eyeball dogbuild start once

### 2026-07-28T03:11:49Z — Persistent dogBuild> terminal interface shipped. `dogbuild start` now opens a branded REPL where DogBuild is the visible interface and Claude Code runs underneath as the execution runtime, one turn per message.

- Implemented:
  - psk/shell.py: dogBuild> REPL — exact prompt, returns to it after every response
  - local state queries (What's happening? / next / tests / remaining / human) answered without invoking Claude
  - built-ins: help, status, next, plan, parked, review, refresh, mode, clear, exit
  - Claude turns via `claude --print` argument list; governor PreToolUse hook and permission mode still in force
  - Claude session kept across turns and recovered across runs via .ai/dogbuild_session.json (gitignored)
  - safe pause with a plain explanation when a human or ChatGPT decision is required; no faked ChatGPT transport
  - launcher default switched to the shell; prior exec behavior preserved behind --raw-claude; new --new-session
  - README quickstart and DogBuild Claude skill updated with the honest interface/runtime/reviewer boundary
- Next safe action: Await ChatGPT review of the persistent dogBuild> slice. Do not begin another slice, push, or publish.
- Unresolved risks:
  - Automatic ChatGPT transport is still not built; reviewer round-trips remain manual.
  - Turns are strictly sequential — no simultaneous side-channel input while Claude is working.
  - Print-mode turns cannot show Claude's interactive permission prompt; a blocked tool call is denied rather than escalated in-line.
  - Commercial demand and payment for DogBuild remain unvalidated.

### 2026-07-28T03:42:48Z — Fixed the three defects the real-terminal PhotoSahi acceptance exposed: turn-scoped owner authorization, the DogBuild skill tool, and stale plain-English orientation.

- Implemented:
  - psk/governor/turngrant.py: turn-scoped owner grant — repository/HEAD/epoch/one-turn bound, repository_read + tests_and_builds only, conservative eligibility, expires after the turn and is swept at shell start and exit
  - broker enforces the grant directly: allows read + existing tests, denies edits/commits/dependencies/network/secrets/out-of-repo/outward-facing itself rather than falling through
  - broker allows Skill only for exactly dogbuild, when installed and identity is valid; arbitrary skills denied; audited as read-only
  - classifier: read-only git plumbing (rev-parse, describe, blame, shortlog, ls-files, read-only remote) is tier 0
  - brief.py: order of truth applied — a checkpoint at an older commit can no longer supply current evidence; a declaration at the live HEAD wins; stale checkpoint demoted to a labelled historical note plus a warning
  - brief.py: no active plan + idle autonomy reports Current task: None / Next step: No task selected / pending-next-milestone, without touching the Goal Contract
  - audit records policy_rule=turn_grant with the grant id on both allows and denies
- Next safe action: Await ChatGPT review of the three defect fixes. Do not begin another slice, push, or publish.
- Unresolved risks:
  - PhotoSahi's ledger still records git_state 5a160ca with 7 reviewer conditions open; the orientation no longer presents it as current, but the closeout itself is an owner decision and was not performed.
  - Turn-grant eligibility is a keyword classifier; a safe instruction phrased unusually will simply get no grant (fails closed, but the owner must rephrase).
  - Automatic ChatGPT transport remains deferred; commercial demand and payment remain unvalidated.

### 2026-07-28T03:57:14Z — Closeout slice approved by the owner and completed. PhotoSahi's ledger is reconciled to 0a36116 with all seven reviewer conditions closed and the owner-away autonomy milestone marked complete; DogBuild's own control-loop milestone is closed and the next milestone is real use plus one outside-user installation test.

- Implemented:
  - psk/review.py satisfy_conditions + `dogbuild review conditions --satisfy`: the missing half of the conditions feature — conditions could be opened but never closed
  - new review_conditions_closed event type and schema entry
  - PhotoSahi: recorded git state moved 5a160ca -> 0a36116; 7 reviewer conditions on ee557880 closed as satisfied; goal revision 3 marks the owner-away autonomy milestone COMPLETE; closeout checkpoint and declaration written; no product code changed
  - DogBuild: goal revision 2 — control-loop milestone COMPLETE; next milestone is real use over several normal work sessions then one outside-user installation test
  - Older records preserved as history throughout: prior goal revisions archived, earlier checkpoints intact, original decision packets untouched
- Next safe action: Use DogBuild normally for real work across several sessions and record what breaks. Build no new feature until that evidence exists.
- Unresolved risks:
  - The review importer splits a wrapped condition across recorded lines; PhotoSahi's 7 conditions were stored as 10 entries. All are closed, so it is cosmetic today, but the parser should be fixed before the next reviewer round-trip.
  - PhotoSahi's .ai/ is untracked by repo policy, so its reconciled ledger exists only on this machine.
  - Automatic ChatGPT transport remains deferred; commercial demand and payment remain unvalidated.

