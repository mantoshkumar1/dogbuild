# Next slices

## Documentation prerequisite — #27

The remote-control product direction must be reconciled into durable
documentation through #27 before the implementation sequence below begins. No
runtime behavior is introduced by that prerequisite; once it has merged, #19 is
the next implementation item.

## Remote-control MVP sequence — not implemented

1. **#19 — local readiness:** prove DogBuild can reconstruct one authoritative
   GitHub issue, execute it locally with Claude, preserve evidence, and resume
   without human context reconstruction.
2. **#24 — durable remote-readable state:** persist every planning-relevant fact
   while keeping ephemeral runtime state local.
3. **#20 — canonical GitHub transport:** define bounded commands and status over
   the existing packet/lineage protocol; do not create a second protocol.
4. **#21 — local watcher:** conservatively poll GitHub, validate identity,
   idempotency, authority, and task ownership before dispatch.
5. **#22 — outbound status:** publish only evidence-backed, meaningful state
   transitions for a remote planner.
6. **#23 — remote-planner proof:** use a planning AI from another device to
   understand one project and continue only already-authorized work.

Only after this single-project loop works repeatedly should DogBuild consider
portfolio orchestration (#25), commercial packaging, or broader integrations.

## Preserved foundation

The historical work on decision outcomes and Claude-to-Codex handoff remains
valuable, but no longer defines the execution sequence. The canonical protocol,
authority gate, evidence checks, and agent-neutral adapters remain prerequisites
for every slice above.
