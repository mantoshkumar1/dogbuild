# Project State Keeper — review request

> Upload this file to ChatGPT and say: **"Review the attached Project State Keeper
> packet."** No other context is needed. It contains no repository source code.

```yaml
packet_type: review_request
packet_id: 84e83faf-8c83-4961-a695-38b8804e0859
project_id: d5c235a5-2c97-44d0-b3cb-a868bdf4fadd
repository_id: 66b750b4-7513-4643-ad59-43f9c8f19f61
project_name: Project State Keeper
repository_name: project-state-keeper
branch: main
head: e8986fe796cd12bd17d5d171cfd04fe45bcda4ba
dirty_fingerprint: null
scope_id: 5f570319-096b-4125-9eae-7057edf78376
scope_revision: 3
packet_created_at: 2026-07-25T20:11:39Z
```

## Question
Should Claude perform the proposed action?

## Active scope (revision 3)
Day 3: first end-to-end manual ChatGPT review happy path

## Current objective
Build Project State Keeper MVP (dogfood-first). Day 1: canonical project-state schema.

## Concise current state
- items: 2 | decisions: 2 | checkpoints: 2
- branch `main` at `e8986fe796cd12bd17d5d171cfd04fe45bcda4ba`
- worktree: clean (ignoring .ai/)

## Proposed action (exact, small, reversible)
Add a new file docs/example-review-workflow.md containing a concise, documented example of the completed manual ChatGPT review workflow (request -> upload -> decision -> import -> gate -> action -> checkpoint). Documentation only; no code changes; fully reversible.

## Local-agent recommendation
Proceed. It is a small, reversible, documentation-only change that records the exact workflow we just built, aiding future use.

## Strongest case against
It adds a doc that must be kept in sync if the workflow changes; minor maintenance. No correctness or safety risk.

## Verification evidence already available
Full local test suite passing at this HEAD: 47 tests, OK.

## Known uncertainty
None material for a documentation-only, reversible action.

## Reserved human-only actions (never auto-performed)
push, merge, deploy, publish, delete data, spend money, external communication, expose secrets, production changes

## Required response format (return exactly this, with values matching the header)
```yaml
schema_version: 1
packet_type: review_decision
packet_id: 84e83faf-8c83-4961-a695-38b8804e0859
project_id: d5c235a5-2c97-44d0-b3cb-a868bdf4fadd
repository_id: 66b750b4-7513-4643-ad59-43f9c8f19f61
reviewed_branch: main
reviewed_head: e8986fe796cd12bd17d5d171cfd04fe45bcda4ba
reviewed_diff_fingerprint: null
scope_id: 5f570319-096b-4125-9eae-7057edf78376
scope_revision: 3
reviewer: chatgpt
decision: APPROVE
confidence: low|medium|high
reviewed_at: <ISO-8601>
```

## Decision
APPROVE

## Rationale
<why>

## Conditions
None

## Required next action
<the exact approved action>

