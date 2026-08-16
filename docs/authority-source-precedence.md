# Authority-source precedence

DogBuild treats visibility as evidence, not authority. Before a branch, pull request,
document, command, decision, or handoff statement can influence execution, the
managed-project adapter supplies live facts to the deterministic
`psk.authority_freshness` evaluator.

The result is one of:

- `CURRENT_AUTHORITATIVE` — a current merged default-branch policy or a current,
  exact-scope founder/strategy promotion;
- `ACTIVE_AUTHORIZED_WIP` — usable only for that same authorized task-local
  workstream, never as repository policy;
- `PAUSED_UNMERGED` — future evidence only;
- `SUPERSEDED_OR_HISTORICAL` — evidence only; or
- `UNKNOWN_OR_CONFLICTING` — fail closed.

Timestamps and AI summaries are intentionally not inputs to precedence. A future
capability visible only in paused WIP is reported as `capability not currently
implemented`, not as a current policy requirement. Callers record every
load-bearing non-main source and the returned classification in bootstrap,
handoff, or reconciliation evidence.

The adapter, not this pure evaluator, is responsible for proving repository identity,
default branch, merge ancestry, PR/task lifecycle, current authorization, and valid
founder/strategy promotion. If it cannot supply those facts, the result fails closed.
