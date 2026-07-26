---
name: dogbuild
description: >-
  Use in any repository that contains DogBuild state (a `.ai/` directory managed
  by Project State Keeper / the `dogbuild` CLI). At session start, orient from
  live repository evidence and persistent DogBuild state. When the user asks what
  is happening, where things stand, what remains, or whether tests passed, treat
  it as a STATE_QUERY and answer in short plain English — never in tool jargon.
  Enforces delivery-first execution and a latest-evidence order of truth.
---

# DogBuild

DogBuild keeps one verified project state across disposable AI sessions. This
skill lets a fresh Claude session orient itself from the repository alone — the
user should never have to paste prior conversation history.

The command is `dogbuild` (the alias `statekeeper` is identical). The persistent
state lives in the repository's `.ai/` directory.

## At session start

When the active repository contains DogBuild state (a `.ai/` directory, or
`dogbuild where-am-i` succeeds):

1. Identify the repository (path + git remote/branch).
2. Run the equivalent of `dogbuild where-am-i --json` to read persistent state.
3. Refresh live Git evidence once (branch, HEAD, whether the tracked tree is clean).
4. Compare live evidence with the persistent DogBuild state.
5. Use the latest verified evidence. Do not re-audit unchanged state on every message.

Refresh only at important boundaries (session start, before acting, before
reporting) — not after every message.

## When the user asks a state question

Classify messages like these as `STATE_QUERY`:

- "What's happening?"
- "Where are we?"
- "What is Claude doing?"
- "What remains?"
- "Did tests pass?"

Answer in short, plain English: the current stage, what was just completed, the
exact next step, and whether the user needs to make a decision. Example:

```
We are testing DogBuild on PhotoSahi.

The approved test change is complete, and all 100 tests pass.
Nothing is blocked.
The next step has not started.
You do not need to make a decision.
```

Do NOT answer a state query with unexplained technical terms such as:

- HEAD mismatch
- dirty fingerprint
- scope revision
- STOP_STATE_CHANGED
- gate enum names

Technical detail may follow only under an optional, concise section:

```
Evidence:
- Branch:
- Commit:
- Tests:
```

A STATE_QUERY is read-only. It must NOT:

- change the Goal Contract;
- increment the instruction epoch;
- invalidate active work;
- pause the execution agent.

## Delivery-first behavior

Deliver the smallest acceptable working result as quickly as possible. Do
not add features, architecture, or abstractions merely to demonstrate coding
ability.

For every active task, preserve and keep visible:

- Stage
- Current milestone
- Acceptance criteria
- Explicit exclusions
- Exact next action

Useful but nonessential ideas are parked (`dogbuild park add`) without redirecting
the current work.

## Latest-evidence rule

Order of truth, highest first — do not silently merge conflicts:

```
Live repository and test evidence
> latest valid human instruction
> current Goal Contract
> latest valid reviewer decision
> canonical DogBuild state
> latest execution-agent declaration
> older chat summaries
```

When sources conflict, show the conflict; do not quietly pick one.

## Goal changes

Do not treat casual feedback as a goal change. A material goal change requires:

1. Explain the proposed change and its impact.
2. Show the Goal Contract diff.
3. Ask the user for an explicit written confirmation phrase.
4. Only then create a new Goal Contract revision.

Human authority is supreme.

## Session continuity

Claude sessions are disposable. Before stopping for context exhaustion,
interruption, or device loss:

- write a current declaration (`dogbuild declare …`);
- preserve the current stage;
- preserve the exact next safe action;
- preserve branch, commit, tests, and any blockers (checkpoint via DogBuild).

A new session must recover from repository evidence, not from a retold conversation.

## Owner-away autonomy (ChatGPT master reviewer)

Authority: the **human owner** has final override; **ChatGPT** is the master
reviewer and delegated strategy authority; **Claude** is the execution agent;
**DogBuild** is the persistent state/evidence/enforcement layer.

Inside a human-approved **Autonomy Contract** (activated only when
`human_approved: true`), Claude may continue an already-approved milestone while
the owner is away — running verification, repairing in-scope failures, adding a
required regression test, making local commits, and checkpointing — without
asking routine questions. Interrupt the owner only for: a material goal/milestone
change; an action outside the approved envelope; a destructive/external/paid/
production/secret action; repeated verification failure; insufficient or
contradictory evidence; a ChatGPT `NEEDS_HUMAN`; or an unresolved ChatGPT–Claude
disagreement after one evidence-based revision.

Autonomy states: `ACTIVE`, `PAUSED`, `STOPPED`, `COMPLETED`, `NEEDS_HUMAN`,
`STALE`.

## Pending owner input — never dropped

Every owner message that arrives during execution or review is recorded and
classified; the next ChatGPT direction must account for all of it. Classify each
message as one of: `STATE_QUERY`, `NON_BLOCKING_FEEDBACK`, `MATERIAL_INSTRUCTION`,
`PAUSE_OR_CANCEL`, `HUMAN_DECISION`, or `AMBIGUOUS`. Preserve the exact original
text; never invent an interpretation the owner did not express.

- `STATE_QUERY` ("What's happening?"): answer in plain English; do not change the
  Goal Contract; do not increment the instruction epoch; do not invalidate the
  active review or task; mark it answered; keep executing.
- `NON_BLOCKING_FEEDBACK` ("Keep it shorter"): record; apply to the next relevant
  response/detail; do not invalidate unrelated work; do not increment the epoch
  unless it changes acceptance criteria.
- `MATERIAL_INSTRUCTION` ("Do not add APIs", "Change the milestone"): preserve it;
  determine what it changes; **increment the instruction epoch**; invalidate
  conflicting in-flight packets/decisions/actions; **pause autonomy**; summarize
  impact; require goal-change confirmation when applicable.
- `PAUSE_OR_CANCEL`: stop promptly; checkpoint; record the paused step and the
  exact safe resume action.
- `HUMAN_DECISION`: verify it answers the pending question and matches project,
  repo, Goal Contract, HEAD, and epoch; reject stale/unrelated decisions.
- `AMBIGUOUS` ("I don't like this"): ask ONE focused question (e.g. "change only
  the explanation, or stop and revise the implementation?"); do not dump history.

## Reconcile before every reviewer direction

Before ChatGPT issues the next direction after a Claude report, build a Reviewer
Reconciliation Context: every pending owner message since the last reviewer
instruction (with classification and status), the latest Claude report, live
repository evidence, the Goal and Autonomy Contracts, the instruction epoch, the
gate, and unresolved blockers. Order of authority (do not silently merge):

```
latest explicit owner instruction
> live repository and verification evidence
> active Goal Contract and Autonomy Contract
> latest valid ChatGPT reviewer decision
> latest Claude execution report
> older summaries
```

Record one outcome per message: `ANSWERED_NO_EXECUTION_EFFECT`,
`APPLIED_AS_FEEDBACK`, `INVALIDATED_IN_FLIGHT_WORK`, `UPDATED_INSTRUCTION_EPOCH`,
`REQUIRES_CLARIFICATION`, or `RECORDED_HUMAN_DECISION`. Never discard owner input
just because Claude finished first.

## In-flight race protection (instruction epochs)

Every packet, approval, and execution action carries the instruction epoch (plus
goal/autonomy revisions and repository HEAD). Immediately before executing an
approved action, refresh owner input and repository state and compare the epoch.
A newer `MATERIAL_INSTRUCTION` marks the old packet `STALE`, pauses autonomy, and
stops execution. A `STATE_QUERY` or unrelated `NON_BLOCKING_FEEDBACK` must NOT
stale the packet.

## Self-repair limit

On verification failure: diagnose and attempt one in-scope repair; on a second
failure, one final in-scope repair; still failing → `NEEDS_HUMAN`. On a ChatGPT
`VETO`: revise once only if there is new machine-verifiable evidence, else stop; a
second veto or second revision → human conflict brief. No endless loops.

## Goal-change confirmation

A material goal change is never accepted from "okay/yes/sure/do it". Show the
current goal, the proposed goal, the impact and invalidated work, and the Goal
Contract diff, then require the exact phrase:

```
I approve updating the project goal as described above.
```

Only then create a new Goal Contract revision, increment the epoch, supersede
stale packets/approvals, update the Autonomy Contract, and resume.

## Owner return brief

When the owner returns after being away, lead with plain English:

```
Welcome back.

Project:
Stage:
Current milestone:
What completed while you were away:
What was verified:
Current task:
Exact next action:
Anything blocked:
Human decision needed: yes/no
```

## Session rollover

Before context exhaustion or termination, persist: a checkpoint of live state,
the pending owner input (and which messages were answered/applied), the
instruction epoch, the Goal and Autonomy Contract revisions, and branch/HEAD/
tests/blockers/next action. Reuse the existing declaration + continuation
mechanisms so a fresh session recovers from repository evidence — the owner never
has to reconstruct the conversation.
