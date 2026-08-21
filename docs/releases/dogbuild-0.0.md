# DogBuild 0.0 — First Official Release

> Founder-verified release-history record. This records DogBuild 0.0 as the
> first official milestone; it does not claim that a `v0.0.0` tag or GitHub
> Release has been created.

## What 0.0 means

**DogBuild 0.0 marks the point where enough real-world dogfooding has been
accumulated to build the DogBuild skill from evidence rather than theory.**

The authoritative operating model has emerged from running real multi-agent
engineering workflows against PingStep.dev. The important outcome is not that
every reusable mechanism is already packaged in DogBuild; it is that the model
now rests on observed operating evidence rather than speculation.

## The milestone

DogBuild began with a practical problem: multiple AI agents could contribute to
a project, but the founder was still acting as their communication transport.

The earlier workflow looked roughly like:

```text
Implementation AI
→ founder relays result
→ strategy/review AI
→ founder relays response
→ implementation AI
```

Through PingStep dogfooding, the workflow evolved toward:

```text
Founder sets direction
→ implementation AI
→ independent review AI
→ correction/reconciliation
→ finalization
→ next authorized task
→ repeat
```

The founder remains the highest authority but should not be required for
routine message forwarding.

**DogBuild 0.0 is the first milestone where the founder verified that multiple
AI agents can operate a real software project without requiring the founder to
relay their routine communication.**

## What has been learned

Enough operating evidence now exists to define the core DogBuild model around:

- durable project identity and state;
- GitHub-backed asynchronous agent communication;
- independent reconstruction of authoritative truth;
- explicit task authorization;
- implementation/reviewer separation;
- material-discovery strategy boundaries;
- bounded reviewer/executor loops;
- fail-closed behavior;
- capability-aware routing;
- issue/branch/PR/commit/CI traceability;
- Project-state reconciliation;
- deterministic next-authority transitions;
- terminal task-close semantics;
- protection against blindly trusting another AI's narration; and
- distinction between current authoritative policy and future, paused, or
  unmerged work.

## PingStep.dev as the proving ground

PingStep.dev has served as the live dogfooding environment and source of the
evidence behind this milestone. The rules were not designed only from
hypothetical architecture. They emerged from real failures and corrections
involving stale project state, cross-agent disagreement, review/fix loops,
capability gaps, GitHub Project inconsistencies, authority boundaries, branch
and repository identity, post-merge reconciliation, task continuation, paused
work, material discoveries, and mistaken interpretation of future/unmerged
governance as current policy.

Many resulting mechanisms have already been implemented and exercised inside
PingStep.dev.

## What is not claimed

DogBuild 0.0 does **not** mean that the reusable DogBuild skill is fully
implemented. The proven mechanisms still need to be extracted from
PingStep-specific implementations where appropriate, generalized, integrated
into DogBuild, packaged as a reusable skill/control system, and validated
against additional projects.

0.0 means sufficient empirical knowledge now exists to perform that work from a
mature operating model rather than speculation. It does not claim that DogBuild
already contains every mechanism proven in PingStep.

## Founder verification

**The founder manually exercised the multi-agent workflow, verified that
routine AI-to-AI coordination no longer inherently requires the founder as the
message bus, and explicitly confirmed DogBuild 0.0 as the first official
release milestone.**

This founder verification is the milestone boundary. It does not replace normal
review, merge, tag, or GitHub Release authority for future implementation
changes.

## The thesis

**PingStep is where DogBuild was discovered. DogBuild is where those proven
operating rules will now be generalized into a reusable system.**

## Status

- Version: DogBuild 0.0
- Milestone: First Official Release
- Founder verification: Confirmed
- Reusable DogBuild skill: Not yet fully implemented
- Empirical operating model: Sufficiently mature to begin extraction and
  generalization
- Primary proving ground: PingStep.dev
- Git tag / GitHub Release: Not created by this record
