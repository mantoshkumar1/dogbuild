# PRODUCT

> Full coordination/control-layer vision, roles, the control loop, and the
> near-term prototype scope vs. the eventual broader product: [`vision.md`](vision.md).

## Problem
When Claude, Cursor, Codex, and ChatGPT work on the same project, they don't
share memory. The human ends up as the manual message bus — copying context,
re-explaining the project, telling one agent what another said, reconstructing
history, and deciding routine matters over and over. Decisions get lost, work
gets duplicated, stale approvals get acted on, and agents silently override each
other.

## What it is
A local, file-based tool that maintains **one canonical, verified project state**
and a **deterministic authority gate**. Agents communicate through structured,
inspectable packets — not hidden conversations. ChatGPT is the delegated reviewer
for routine, reversible, in-scope decisions; the human is the ultimate authority
and is interrupted only on real exceptions.

## Framing (recorded, honest)
**Founder-tool-first (dogfood).** Built because the founder has a genuine
recurring problem and will use it daily. It is a **time-boxed commercial
experiment, not an indefinite personal automation project.**

The path:
1. Solve my own cross-agent coordination problem.
2. Prove it across real projects.
3. Package the working system as a sellable skill / CLI.
4. Test whether unrelated users will pay.
5. **Park it if the commercial evidence is weak.**

Dogfood usefulness is **not** demand. Payment, external demand, pricing, and
distribution stay unvalidated until step 4 — see
[`docs/commercial-assumptions.md`](docs/commercial-assumptions.md).

## Positioning lines (for later, not commitments)
- *Your coding agents communicate with each other. You step in only when they disagree.*
- *Give one AI authority. Let the others execute. Get interrupted only when the decision genuinely needs you.*

## Founder-first delivery boundary

The completed local-only MVP proved a protocol and a founder workflow; it did
not remove the routine relay burden. The current product direction is to prove
one **local runtime + GitHub rendezvous** loop for the founder before considering
commercial packaging. This is a product-necessity sequence, not a commitment to
hosted infrastructure or a paid tier.

**Already built (local foundation):**
- canonical project-state schema + local CLI;
- state init & checkpointing;
- evidence-backed status reconstruction (git + state file);
- agent handoff generation;
- ChatGPT Web review-request (packet) generation via manual file exchange;
- structured review-decision import;
- stale-decision + repository-identity/branch/commit validation;
- deterministic authority gate (APPROVE / APPROVE_WITH_CONDITIONS / VETO / NEEDS_HUMAN);
- thin Claude / Cursor / Codex adapters over one canonical protocol;

**Next to prove (not built yet):**
- one local runtime safely executes one GitHub-authorized issue;
- planning-relevant facts become durable and GitHub-visible;
- GitHub carries bounded commands and meaningful evidence-backed status;
- a planning AI can resume one project remotely without the owner acting as a
  courier; and
- all irreversible actions remain owner-controlled.

**Later commercial/product possibilities — hypothesis only:**
- alternative planner integrations, including an API where evidence justifies it;
- multi-repo / workspace orchestration;
- shared/team state;
- richer conflict reports and analytics;
- hosted sync / dashboard;
- additional adapters, templates, priority support.

If the commercial test (step 4) is weak, those later capabilities are not built
and DogBuild remains a founder utility.

## Validated problems & product principles (added 2026-07-25)

The Day 3 acceptance run validated two more founder problems.

### 1. Routine transport must not interrupt the user
```yaml
problem: manual-cross-agent-transport
founder_problem_status: validated
commercial_status: unvalidated
```
The manual run required the user to locate a file, upload it to ChatGPT, copy the
decision, and return it. That **proves the protocol but fails the intended product
experience.**

**Principle:** *The user must not act as a routine courier between ChatGPT, Claude,
and Codex.* Interrupt the user only for: `VETO`; `NEEDS_HUMAN`; an unresolved agent
disagreement; insufficient evidence; stale/mismatched context that cannot be
refreshed automatically; or irreversible/externally-consequential actions. The
remote-control MVP is the planned proof of automatic routine transport,
verification, and continuation. **It does not exist yet** — manual exchange is a
temporary proof mechanism, not the target experience.

### 2. Founder orientation loss
```yaml
problem: founder-orientation-loss
frequency: recurring
founder_problem_status: validated
personal_validation_ability: strong
commercial_status: unvalidated
```
The user can lose track *inside their own work* — what is being built, which phase
is active, why the current task exists, and how the latest Claude reply / latest
ChatGPT decision / repository state relate — even when machine state exists.

**Principle:** *Project state must be understandable to the human owner in seconds,
not only machine-readable by agents.* See [`docs/orientation-brief.md`](docs/orientation-brief.md).
