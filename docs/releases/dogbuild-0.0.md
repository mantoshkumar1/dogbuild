# DogBuild 0.0 — First Official Release

> Release candidate notes. This release is not cut until the linked implementation
> is merged, exact merged tests pass, PingStep dogfooding is read back, and a human
> creates tag `v0.0.0` on that exact verified commit.

## Core guarantee

DogBuild distinguishes current authoritative project state from active WIP,
paused/unmerged future work, and historical/superseded state before allowing a
referenced source to influence execution. Ambiguous authority fails closed.

## Dogfooding proof

PingStep #217 / #240 / PR #242 showed why this is required: a future
`governance:handoff` command was visible in paused, unmerged work but was not
current main policy. DogBuild classifies that source as `PAUSED_UNMERGED`, returns
the current-main replacement, and reports the command as a capability not currently
implemented rather than a false current-policy requirement.

## What 0.0 proves

- durable cross-agent state reconstruction;
- authority-aware evidence precedence;
- current-versus-future policy separation;
- material-discovery stop and strategy routing;
- bounded review behavior;
- task-scoped authorization; and
- fail-closed behavior when authority is ambiguous.

## What 0.0 does not guarantee

- automatic GitHub, provider, or browser evidence collection; adapters must still
  supply live facts to the deterministic evaluator;
- automatic cross-provider reviewer transport;
- permission to merge, tag, publish a release, deploy, or bypass repository
  policy; and
- that any visible future branch capability is present on current main.

## Release record to create after finalization

- Version: `0.0.0`
- Tag: `v0.0.0`
- Title: `DogBuild 0.0 — First Official Release`
- Commit: exact merged, CI-verified authority-precedence implementation commit
