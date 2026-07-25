# Project State Keeper — agent handoff

> The instruction below originated from the **delegated reviewer AI (ChatGPT)** and
> was transported through Project State Keeper. The receiving agent (claude)
> **must verify this repository** (identity, branch, HEAD, scope, freshness) before
> acting. This packet contains no repository source code.

```yaml
packet_type: agent_handoff
packet_id: baa8e579-593d-42f2-b00a-d99a38062c0c
project_id: d5c235a5-2c97-44d0-b3cb-a868bdf4fadd
repository_id: 66b750b4-7513-4643-ad59-43f9c8f19f61
project_name: Project State Keeper
repository_name: project-state-keeper
branch: main
head: 019f519bdc8b2fced7bf2e7197d7b62e028180d1
diff_fingerprint: null
scope_id: 5f570319-096b-4125-9eae-7057edf78376
scope_revision: 4

source_agent:
  actor_type: ai_execution_agent
  actor_name: claude
  role: execution_agent

target_agent:
  actor_type: ai_execution_agent
  actor_name: claude
  role: execution_agent

instruction_source:
  actor_type: ai_reviewer
  actor_name: chatgpt
  role: delegated_strategy_authority

human_override: always
```

## Original objective
Build Project State Keeper MVP (dogfood-first). Day 1: canonical project-state schema.

## Current phase
Day 4: Orientation Brief + generic handoff slice (scope revision 4)

## Exact delegated task
Add a CLI-level test confirming `statekeeper where-am-i` is an alias of `statekeeper brief` for human-readable output (JSON alias already covered), and add one concise `where-am-i` command example to the documentation.

## What already exists
- 3 decisions, 3 checkpoints, 1 reviews recorded
- branch `main` at `019f519bdc8b2fced7bf2e7197d7b62e028180d1`

## What was verified
47 unittest tests green after the approved action

## Failures and resolutions
None recorded at this checkpoint.

## Relevant files
The repository at its verified HEAD; `.ai/STATE.md` for the current projection.

## Prohibited actions
push, merge, deploy, publish, delete data, spend money, external communication, expose secrets, production changes

## Acceptance criteria
New human-alias CLI test passes; full suite green; a doc example added.

## Exact next safe action
Perform only the delegated test + doc change; then checkpoint.

## Required completion declaration (the receiving agent must return this)
```text
What are we building?
What did I change?
What did I actually verify?
What failed and how was it resolved?
What remains incomplete?
What is the exact next safe action?
```
