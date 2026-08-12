# DogBuild Remote-Control Vision — Draft Preservation Note

This file intentionally preserves the product direction clarified on 2026-08-11 so it is not lost before formal documentation reconciliation.

## Core operating model

DogBuild is the persistent coordination and authority layer between a human owner, a strong planning AI, execution agents, GitHub, and durable repository state.

The target interaction is not that the human manages Claude, Codex, or Cursor directly. The human manages intent, priorities, constraints, and consequential decisions through one strong planning AI. DogBuild preserves project truth, routes work, enforces authority, and carries the execution state between planning and implementation layers.

```text
Human owner
    ↓
Strong planning AI (initially ChatGPT)
    ↓
GitHub-visible DogBuild state + coordination messages
    ↓
Local DogBuild runtime on execution machine
    ↓
Claude / execution agent
    ↓
repository / tests / PR / CI
    ↓
DogBuild publishes evidence-backed state to GitHub
    ↓
planning AI makes the next judgment
```

## Important architectural split

- Repository DogBuild state is the durable project memory.
- GitHub is the asynchronous rendezvous/transport surface between remote planning AI and local execution.
- Local DogBuild runtime owns transient operational state such as running sessions, polling cursors, retries, locks, temporary worktrees, and logs.
- Anything required for future planning or recovery must become durable and GitHub-visible.
- GitHub comments should carry meaningful coordination events, not high-frequency runtime chatter.

## Intended user experience

The owner should be able to leave the development computer, later open ChatGPT from a phone or another device, ask what happened, make only decisions requiring judgment, and allow work to continue without manually transporting Claude output, review results, or project context.

Example:

1. Planning AI identifies the highest-priority authorized task.
2. It posts a structured DogBuild command through GitHub.
3. Local DogBuild detects the command and dispatches Claude.
4. Claude implements within the approved scope.
5. DogBuild verifies repository evidence, updates durable project state, and posts a structured status/review/decision request to GitHub.
6. Planning AI reads that state remotely and decides the next safe action.
7. Material product/architecture/authority changes stop for the appropriate decision rather than being silently self-approved.

## Product principle

Workers are replaceable. Planning models are replaceable. Project memory, authority, evidence, and lineage must survive all of them.

DogBuild should therefore not attempt to become the strongest reasoning model. It should make a strong external planning AI capable of safely managing one or more execution agents without the human becoming the scheduler, message bus, or memory layer.

## Near-term sequencing

1. Prove DogBuild's local Claude execution loop is trustworthy.
2. Ensure planning-relevant state is durable and GitHub-visible.
3. Define the GitHub coordination protocol using DogBuild's existing canonical packet/lineage model.
4. Implement safe local polling for commands.
5. Publish evidence-backed status back to GitHub.
6. Prove ChatGPT can remotely plan and continue one project from another device.
7. Only after that, expand to portfolio-level discovery/prioritization across DogBuild-enabled repositories.

## Defining test

Can the owner leave the development computer, later open a planning AI from another device, understand exactly what happened, make only the decisions requiring judgment, and allow the software project to continue without manually carrying messages between AI agents?

This draft is a preservation artifact. The authoritative product docs (`vision.md`, `PRODUCT.md`, `docs/mvp-scope.md`, `docs/next-slices.md`, and related authority/state docs) must be reconciled through the corresponding high-priority documentation issue before this direction is treated as fully adopted product scope.
