# Example: the manual ChatGPT review workflow

A concise, worked example of one complete Project State Keeper review round-trip:

```text
request → upload → decision → import → gate → action → checkpoint
```

This is the **manual proof mechanism** (Day 3). It demonstrates the protocol; it is
**not** the target product experience — see *Limitation* at the end.

## The seven steps

### 1. Request — the execution agent proposes one small, reversible action
```bash
statekeeper review request \
  --question "Should Claude perform the proposed action?" \
  --action "Add docs/example-review-workflow.md (documentation only, reversible)"
```
Writes a self-contained packet to
`.ai/exchange/outbox/<packet-id>-chatgpt-review.md`. The packet carries the
project/repository identity, branch, full HEAD, diff fingerprint, scope id +
revision, the proposed action, the local-agent recommendation, the strongest case
against, available evidence, known uncertainty, the reserved human-only actions,
and the exact response format required — **no repository source code.**

### 2. Upload — the human hands the packet to the reviewer
Attach the packet in ChatGPT Web and say: *"Review the attached Project State
Keeper packet."* No other context is needed.

### 3. Decision — ChatGPT returns a structured verdict
The reply repeats the identity header **unchanged** and gives a `decision`
(here `APPROVE`), rationale, conditions (`None`), and the required next action.

### 4. Import — validate and record (never execute)
```bash
statekeeper review import <decision-file>
```
Validation rejects a decision whose packet id is unknown, or whose project id,
repository id, branch, HEAD, diff fingerprint, or scope id/revision does not match
the request — protecting you even if a reply is copied from the wrong chat. The
original request and decision are archived **unchanged** under
`.ai/exchange/archive/<packet-id>/`, and the decision is recorded in canonical
state. Import performs **no** action.

### 5. Gate — authorize only the exact approved action
```bash
statekeeper review gate
# → result: PROCEED   (APPROVE + approval still current)
```
`PROCEED` authorizes **only** the exact proposed action. It never authorizes push,
merge, deploy, publish, delete, spend, external communication, secrets, or
production changes.

### 6. Action — perform only what was approved
The execution agent makes exactly the approved change (this file) — nothing else.

### 7. Checkpoint — record the verified result
A checkpoint captures what was implemented, what was verified, current git state,
and the exact next safe action, so the next session resumes without reconstructing
context.

## Worked values from the real Day 3 acceptance run
```text
packet_id:  84e83faf-8c83-4961-a695-38b8804e0859
project:    Project State Keeper
branch:     main
head:       e8986fe796cd12bd17d5d171cfd04fe45bcda4ba
scope:      5f570319-… (revision 3)
decision:   APPROVE (reviewer: chatgpt, confidence: high)
gate:       PROCEED (approval_current: true)
```

## Limitation (important)
This flow required the human to act as a **courier** — locate a file, upload it,
copy the decision back. That is a **temporary proof mechanism, not the target
product experience.** The intended product interrupts the human only for `VETO`,
`NEEDS_HUMAN`, unresolved agent disagreement, insufficient evidence,
unrefreshable stale/mismatched context, or irreversible actions — not for routine
transport. That automation does **not** exist yet.
