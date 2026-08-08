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
