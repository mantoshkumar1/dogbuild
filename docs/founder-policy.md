# Founder policy (versioned snapshot; enforcement not yet implemented)

DogBuild must eventually enforce the founder's binding commercial constraints.
Their upstream decision source is the private Revenue Opportunity Lab. The
versioned DogBuild-owned snapshot is
[`product-governance-source.md`](product-governance-source.md); runtime behavior
must never depend on the Lab being present on the local machine.

**Status: NOT implemented.** DogBuild's machine-readable Goal Contract does not yet
carry founder-policy fields. This document records the requirement so it is not
forgotten and is not mistaken for completed functionality. When implemented, it must
be a **small governance-data change** that does **not** alter the current
implementation milestone, and it must go through the normal review/gate flow.

## Constraints future Reality Checks / Goal Contracts must enforce
- **Founder-only before revenue** — no employees/contractors/partners/agencies until
  sustained revenue (legal/security emergency + explicit human approval excepted).
- **Low direct operating cost; no unnecessary hosted infrastructure.**
- **No silent paid API consumption** — automated mode must use **customers' own API
  credentials and provider billing (BYOK)**, not founder-absorbed model costs.
- **One active product** — no new active product while DogBuild is active; optional
  ideas are **parked**, not implemented.
- **Six-month first-payment window begins at launch**, not at the start of private
  development; launch is required.
- **Early stop only on evidence** against the central commercial hypothesis.
- **Human authority** over activation, abandonment, spending, hiring, and scope.

## First financial milestone
`product_self_funding` — recover **direct** product costs (hosting, domain,
marketplace/payment fees, product-specific API usage, unavoidable maintenance).
Founder labour and existing general-purpose ChatGPT/Claude/Codex subscriptions and
ordinary laptop/internet **do not count**.

## Reality-check policy (to implement later)
```text
New proposal → compare with active Goal Contract + Founder Knowledge Contract
  Necessary and in scope                        → continue
  Useful but outside current milestone          → park and continue (no human interrupt)
  Contradicts a binding founder constraint      → stop and ask one focused human question
  Invalidates the core hypothesis (new evidence)→ surface evidence, request continue/park/kill
```

**Commercial status:** demand, payment, and distribution remain **unvalidated**.
Dogfood usefulness is not demand.
