# Project State Keeper

A local, file-based **communication and authority layer** between coding agents
(Claude Code, Cursor, Codex) with **ChatGPT** as the delegated reviewer and the
**human owner** in ultimate authority. It keeps every agent operating from **one
verified project state**, routes routine decisions through a deterministic
authority gate, and interrupts the human only on real exceptions.

> Your coding agents coordinate through a verified state ledger instead of hidden
> conversations. You step in only when a decision genuinely needs you.

## Status

- **Phase:** two-week MVP (founder tool / dogfood).
- **Framing:** built because the founder already needs it. Selling it is a
  **hypothesis to test later** — payment, demand, pricing, and distribution are
  **explicitly unvalidated** (see [`docs/commercial-assumptions.md`](docs/commercial-assumptions.md)).
- Product source of truth: the spec in `revenue-opportunity-lab`
  (`ideas/active/project-state-keeper.md`), refined by the docs here.

## Scope discipline (MVP)

Local-only · file-based · **no** OpenAI API · **no** browser automation · **no**
hosted backend · **no** accounts · **no** payment · **no** dashboard · **no**
cloud sync. One canonical protocol; thin per-agent adapters (never four
implementations).

## Docs

| Doc | Purpose |
|---|---|
| [`PRODUCT.md`](PRODUCT.md) | What it is, dogfood→commercial path, Lite vs Pro. |
| [`docs/authority-model.md`](docs/authority-model.md) | Roles, gate hierarchy (human > ChatGPT > agents > keeper), gate behavior. |
| [`docs/mvp-scope.md`](docs/mvp-scope.md) | Exactly what's in and out of the two-week MVP. |
| [`docs/execution-plan.md`](docs/execution-plan.md) | 14-day build plan. |
| [`docs/success-and-kill-criteria.md`](docs/success-and-kill-criteria.md) | When it worked; when to park it. |
| [`docs/commercial-assumptions.md`](docs/commercial-assumptions.md) | Unresolved, unvalidated commercial questions. |

Human retains authority over all irreversible actions (push, deploy, merge,
publish, delete, spend, external comms, secrets/production, scope changes).
