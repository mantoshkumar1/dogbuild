# Authority Model

## Corrected gate hierarchy (authoritative)
Human authority is **above** every agent. ChatGPT is a **delegate**, not the
owner.

```text
Human owner
    ↓ delegates routine authority
ChatGPT reviewer           (routine, reversible, in-scope decisions only)
    ↓ approves or vetoes
Claude / Cursor / Codex    (execution agents — act only within approved scope)
    ↓ act
Project State Keeper       (verifies state, enforces gates — makes no product decisions)
```

ChatGPT is the delegated final reviewer for **routine, reversible, within-scope**
technical/product decisions. It is **not** the ultimate owner of the project.

## Roles

### Execution agent — Claude, Cursor, or Codex
Inspects the local repo; proposes decisions; writes code; runs tests; gathers
evidence; generates review requests; follows imported review decisions;
checkpoints state. **Not** the final authority when a ChatGPT gate is active.

### Project State Keeper — neutral verification layer
Maintains canonical state; transports review requests/decisions; verifies repo
identity, branch, commit; rejects stale/mismatched decisions; records conditions,
objections, outcomes; prevents silent overrides; decides whether execution may
proceed via **deterministic gate rules**. Makes **no** product/architecture
decisions.

For a proposed new task, the same boundary applies before an issue is created:
DogBuild must re-derive repository identity, current task/PR state, active
dependencies, duplicate or superseded owners, and alignment with the approved
vision and sequence. If an existing owner covers the work, it must link that
owner rather than create a duplicate. If the proposal changes scope, priority,
sequencing, acceptance evidence, or authority, DogBuild must stop for the
appropriate strategy or human decision instead of self-authorizing a ticket.

### ChatGPT — delegated reviewer
Returns `APPROVE` · `APPROVE_WITH_CONDITIONS` · `VETO` · `NEEDS_HUMAN`. When a
valid, current decision exists, execution agents **must respect it** and may not
silently override a veto or ignore conditions. Authority is **delegated** by the
human and bounded to routine, reversible, in-scope matters.

### Human owner — ultimate authority
Not required to carry context between agents. Interrupted **only** on real
exceptions (below). Retains final say always.

## Human approval always required
Push · deployment · merge · publication · destructive/data-deleting changes ·
spending · external communication · secrets or production access · **scope
changes** · conflicts ChatGPT cannot resolve · anything irreversible or
externally consequential · anything the human explicitly reserved.

## Human is interrupted only when
- ChatGPT returns `VETO`;
- ChatGPT returns `NEEDS_HUMAN`;
- the execution agent materially disagrees with ChatGPT (with new evidence);
- the decision is stale or invalid;
- evidence is insufficient;
- a requested action is irreversible/externally consequential;
- the human explicitly reserved the decision.

## Default control loop
```text
User defines objective once
        ↓
Claude / Cursor / Codex performs local work
        ↓
Execution agent creates verified review packet
        ↓
ChatGPT reviews the packet
        ↓
Project State Keeper imports and validates the decision
        ↓
APPROVE                 → execution continues
APPROVE_WITH_CONDITIONS → execution continues within conditions
VETO                    → execution stops, user shown the disagreement
NEEDS_HUMAN             → execution stops, user gets one focused question
```

## Gate behavior

**APPROVE** — perform the exact approved next action without re-asking. Scope
limited to the reviewed repo, branch, commit, stated scope, and proposed action.
Not authorization for unrelated work.

**APPROVE_WITH_CONDITIONS** — proceed only after converting **every** condition
into a tracked requirement. Stop if a condition can't be met, satisfying it
materially changes scope, new evidence contradicts the approval, or the repo
changes enough to invalidate the reviewed state.

**VETO** — stop. Present a compact conflict report (local recommendation /
ChatGPT decision / precise disagreement / evidence each side / options /
recommended human question). Show only the decision-relevant conflict.

**NEEDS_HUMAN** — stop; ask **one** focused question including why human judgment
is required, the choices, each consequence, and a default recommendation when one
exists.

**Stale / invalid decision** — do not proceed under the old approval;
automatically prepare a refreshed review request describing what changed.

**Local-agent disagreement** — an agent may challenge a decision **only** with new
local evidence ChatGPT didn't review. It must: record the disagreement; attach the
evidence; generate a revised packet; request another decision; stop until the new
decision is imported. It may never simply ignore the decision.
