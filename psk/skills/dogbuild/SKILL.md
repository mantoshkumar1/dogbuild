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
