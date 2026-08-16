Refs #<issue> — partial; issue remains open
<!-- For a PR that fully completes one issue, replace the line above with the plain, unformatted
     directive `Closes #<issue>`. Delete this comment before submitting. -->

## PR presentation contract

Keep one execution record on the authoritative issue while making that record easy to find from this PR.

- **Authoritative issue:** #<issue> — current execution status (for example, `In Progress`, `In Review`, or
  `Done`).
- **Project record:** Issue #<issue> in the configured GitHub Project — PR not a Project item.
- **PR role:** full implementation / partial slice / reconciliation — state this PR's actual purpose.
- **Closing semantics:** `partial slice` / `full completion`; this must match the plain top-of-body directive.

## Scope

- **Objective / task:** what this PR does, in plain language.
- **Relates to:** GitHub issue, or the `.ai/state.json` requested-item id, if any.
- **Out of scope:** what a reviewer should not expect here.

## Evidence

- **Tests:** `python -m unittest discover -s tests` — CI runs this on every push and PR against `main`
  (Python 3.9 and 3.11). Do not paste routine passing logs here; note only failures or gaps CI doesn't cover.
- **Manual verification (if any):**

## State handoff

- **Did this change `.ai/state.json` / `.ai/STATE.md`?** Yes / No
- **Reserved approvals touched** (per [`docs/authority-model.md`](../docs/authority-model.md) — push,
  deployment, merge, publication, destructive/data-deleting changes, spend, external communication, secrets or
  production access, scope changes): none / list them

## Merge authority

Per [`docs/authority-model.md`](../docs/authority-model.md), push, deployment, merge, and publication always
require human approval, regardless of what CI or a delegated reviewer decided. No AI agent merges this PR into
`main` — the human owner performs the final merge after reviewing CI and the evidence above.
