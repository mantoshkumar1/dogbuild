---
name: dogbuild
description: >-
  Use in any repository that contains DogBuild state (a `.ai/` directory managed
  by DogBuild / the Project State Keeper subsystem). At session start, orient from
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

## The DogBuild interface

`dogbuild start` opens a persistent `dogBuild>` prompt. The user talks to
DogBuild; Claude Code runs underneath as the execution runtime, one turn per
message. When you are invoked this way:

- Do not tell the user to "run Claude" or refer to the Claude UI — from where
  they sit, they are using DogBuild.
- Keep each turn self-contained and short. The user returns to `dogBuild>`
  immediately after your reply, so there is no scrollback to lean on.
- Persist anything that matters to `.ai/` before the turn ends. The next turn
  may be a different session.
- ChatGPT remains the master reviewer, and DogBuild has **no** automatic
  ChatGPT transport. If a reviewer decision is needed, say so plainly and stop
  — never imply the message was sent.

DogBuild answers simple state questions itself, without invoking Claude. If a
state query does reach you, answer it as described below.

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

## Execution plan sync

When starting a genuinely complex task (multiple acceptance criteria, several
implementation steps), create a short execution plan (3–7 steps) derived from:

- the active Goal Contract
- current milestone
- acceptance criteria
- explicit exclusions
- exact next action

Do not create a large backlog. The plan is a session aid, not a project database.

### What to persist

Session-local detail (a Claude todo list inside one session) is NOT persisted.
At meaningful boundaries (checkpoint, commit, verification, pause, session
rollover, task completion), persist only decision-relevant progress:

- completed steps
- current step
- remaining acceptance criteria
- blockers
- exact next safe action

### Scope protection

The active execution plan must contain only work needed for the current milestone.

- Necessary for acceptance → add to the current plan.
- Useful but not necessary → park it and continue.
- Materially changes the goal or milestone → stop and request a formal human decision.

Do not let optional ideas silently enter the active plan.

### Simple tasks

Simple tasks (a quick fix, a single-file change, a state query) do not need an
execution plan. Only create one when the task has enough moving parts that
losing context mid-task would cost real recovery time.

### Answering state queries during execution

When the user asks "What's happening?" or "What remains?" during an active plan,
answer from the current plan in plain English. A state query must not pause
execution, change the goal, invalidate the task, or increment the instruction
epoch. Example:

```
We are improving DogBuild's execution tracking.

Completed: state-model update.
Current task: update the skill.
Remaining: add tests, run full verification.

Nothing is blocked.
You do not need to make a decision.
```

### Session recovery

A fresh session must reconstruct the active plan from persistent DogBuild state
(the execution_plan field in state.json) without asking the user to repeat what
happened. Always prioritize delivery over displaying coding sophistication.

## Session continuity

Claude sessions are disposable. Before stopping for context exhaustion,
interruption, or device loss:

- write a current declaration (`dogbuild declare …`);
- update the execution plan if one is active;
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

## Permission governance (DogBuild governor)

When DogBuild launches Claude Code (`dogbuild start`), it installs a PreToolUse
hook that routes every tool call through the DogBuild governor's permission
broker. The broker classifies each action and returns allow or deny — safe
routine actions execute without repeated yes/no dialogs.

### What is auto-approved

- **Read-only tools** (Read, Glob, Grep, etc.) targeting paths inside the
  repository.
- **In-repository file edits** (Edit, Write) that are not in `.git/`, not
  secret/credential files, and not protected by policy.
- **Safe bash commands** classified by the governor as read-only or task-scoped
  per the active execution policy (git status, git diff, git log, test runners,
  linters, DogBuild internal commands).
- **Subagent spawns** (Task, Agent).

### What is denied

- Paths outside the repository (path escape).
- Writes to `.git/` internals.
- Writes to secret/credential files (`.env`, `id_rsa`, `.pem`, `.key`, etc.).
- Writes to policy-protected paths.
- Hard-denied commands: `git push`, `git merge`, `git rebase`, deployment,
  `sudo`, `rm -rf`, network upload, package publication, paid API calls,
  secret access, production changes.
- Commands requiring human approval (per policy).
- MCP tools (require human review).
- Unknown tools not covered by policy.

### What a denial looks like

A denial pauses the affected action safely. Nothing is lost. The broker
provides a plain-English explanation:

```
Claude requested an action outside the approved working boundary.

Requested action: Bash
Reason it stopped: git push is denied by policy

Current work is safely paused.
Nothing has been lost.
```

### Raw-Claude mode

`dogbuild start --raw-claude` skips the governor hook and uses Claude Code's
native permission mode. Use this when you want direct control over Claude Code's
built-in permission dialogs without the DogBuild policy layer.

### Governor CLI commands

- `statekeeper governor status` — overview of policy, autonomy, hook status
- `statekeeper governor explain-last` — plain-English explanation of last decision
- `statekeeper governor test` — run built-in test fixtures
- `statekeeper governor broker` — hook entry point (reads stdin, writes stdout)

## Session rollover

Before context exhaustion or termination, persist: a checkpoint of live state,
the pending owner input (and which messages were answered/applied), the
instruction epoch, the Goal and Autonomy Contract revisions, and branch/HEAD/
tests/blockers/next action. Reuse the existing declaration + continuation
mechanisms so a fresh session recovers from repository evidence — the owner never
has to reconstruct the conversation.
