# DogBuild

[![CI](https://github.com/mantoshkumar1/dogbuild/actions/workflows/ci.yml/badge.svg)](https://github.com/mantoshkumar1/dogbuild/actions/workflows/ci.yml)

A local, file-based **project interface and authority layer** between coding agents
(Claude Code, Cursor, Codex) with **ChatGPT** as the delegated reviewer and the
**human owner** in ultimate authority. It keeps every agent operating from **one
verified project state**, routes routine decisions through a deterministic
authority gate, and interrupts the human only on real exceptions.

> Your coding agents coordinate through a verified state ledger instead of hidden
> conversations. You step in only when a decision genuinely needs you.

## Motivating workflow

DogBuild grew out of coordination friction the founder hit while building
[PingStep](https://pingstep.dev/): implementation done by one coding agent, review done separately by
another, with the human manually carrying the implementation result to the
reviewer and the review findings back — every round of fixes. PingStep is a
motivating example, not a DogBuild dependency or customer; day-to-day
dogfooding currently runs against PhotoSahi and DogBuild itself (see Quickstart
below). That manual transport is still how the alpha works — DogBuild does not
yet automate it (see "What is actually running" below). Full account:
[`vision.md`](vision.md).

## Status

- **Phase:** two-week MVP (founder tool / dogfood).
- **Framing:** built because the founder already needs it. Selling it is a
  **hypothesis to test later** — payment, demand, pricing, and distribution are
  **explicitly unvalidated** (see [`docs/commercial-assumptions.md`](docs/commercial-assumptions.md)).
- DogBuild's product activation and commercial constraints originated in the
  private Revenue Opportunity Lab. DogBuild owns its implementation and runtime
  truth. See [`docs/governance-boundaries.md`](docs/governance-boundaries.md) and
  the versioned [`docs/product-governance-source.md`](docs/product-governance-source.md)
  snapshot.
- **Tests run in CI, not just locally.** Every push and pull request against
  `main` runs the full suite (`python -m unittest discover -s tests`) on Python
  3.9 and 3.11 — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml). Merge
  authority itself is still human-only regardless of CI result; see
  [`docs/authority-model.md`](docs/authority-model.md).

## Quickstart

```bash
# 1. cd into your project
cd ~/Desktop/project/your-project

# 2. Initialize DogBuild (first time only)
dogbuild init . --objective "your project objective"

# 3. Launch DogBuild
dogbuild start
```

You land on the DogBuild prompt:

```
DogBuild

  Project:            PhotoSahi
  Stage:              PhotoSahi maintenance
  Current milestone:  <live milestone>
  Last verified:      <live verification>
  Human needed:       No

dogBuild>
```

`dogBuild>` is the project interface. Ask **"What's happening?"** at any time,
or type `help` for the built-in commands. After every completed response the
terminal returns to `dogBuild>`.

### What is actually running

- **DogBuild is the visible interface.** You talk to DogBuild, not to a
  coding agent.
- **Claude Code is the current execution runtime.** It runs underneath, one
  turn per message. It can be replaced without losing the project.
- **ChatGPT is the master reviewer.** DogBuild does **not** talk to ChatGPT
  automatically — transport is manual in this alpha. When a reviewer decision
  is required DogBuild pauses and tells you so; it never pretends to have sent
  anything.
- **Persistent truth lives in the repository's `.ai/` state**, not in the
  Claude session. Sessions are disposable; the project is not.
- **The human is the final authority.** Anything needing a human decision
  blocks dispatch.

### Start options

```bash
dogbuild start                              # persistent dogBuild> interface
dogbuild start <repository-path>            # a specific repository
dogbuild start --dry-run                    # show what would happen; start nothing
dogbuild start --raw-claude                 # exec Claude Code directly (no DogBuild shell)
dogbuild start --new-session                # ignore the recovered Claude session
dogbuild start --permission-mode acceptEdits
```

`statekeeper …`, `psk …`, and `dogbuild …` remain interchangeable.

Initialization is independent by default. An upstream product or governance
record is optional and must be supplied explicitly with `--source-name` and
`--source-record`; DogBuild never injects the founder's private Lab into another
user's repository.

### Built-in commands

Answered from local state — no Claude call, no tokens spent:

| Command | Shows |
|---|---|
| `help` | the command list |
| `status` | live project status in plain English |
| `next` | the exact next action |
| `plan` | execution plan and distance to delivery |
| `parked` | parked ideas |
| `review` | reviewer gate and how to get a ChatGPT decision (manually) |
| `refresh` | re-read live Git evidence and DogBuild state |
| `mode` | runtime, permission mode, session |
| `clear` | clear the screen |
| `exit` / `quit` | leave DogBuild (Ctrl-D also works) |

Plain questions like "What's happening?", "What's next?", "Did the tests pass?"
are answered the same way. Anything else is a real instruction and goes to
Claude Code.

### Share a short status

Write a small report to any folder you choose. This is useful when you keep a separate, shared status area for your projects.

```bash
dogbuild report . --output-dir /path/to/reports/dogbuild \
  --changed "Added the report command" \
  --worked "Focused tests pass" \
  --blocked "Nothing" \
  --next "Open the pull request"
```

Each answer must be one short line. DogBuild does not copy project files, source code, or command output into the report, and it refuses obvious secret values. Pick the output folder yourself; DogBuild never hard-codes one.

## Scope discipline (MVP)

Local-only · file-based · **no** OpenAI API · **no** browser automation · **no**
hosted backend · **no** accounts · **no** payment · **no** dashboard · **no**
cloud sync. One canonical protocol; thin per-agent adapters (never four
implementations).

## Docs

| Doc | Purpose |
|---|---|
| [`vision.md`](vision.md) | Full product vision: coordination/control layer, roles, control loop, first prototype vs. eventual product, milestone roadmap. |
| [`PRODUCT.md`](PRODUCT.md) | What it is, dogfood→commercial path, Lite vs Pro. |
| [`docs/authority-model.md`](docs/authority-model.md) | Roles, gate hierarchy (human > ChatGPT > agents > keeper), gate behavior. |
| [`docs/mvp-scope.md`](docs/mvp-scope.md) | Exactly what's in and out of the two-week MVP. |
| [`docs/execution-plan.md`](docs/execution-plan.md) | 14-day build plan. |
| [`docs/success-and-kill-criteria.md`](docs/success-and-kill-criteria.md) | When it worked; when to park it. |
| [`docs/commercial-assumptions.md`](docs/commercial-assumptions.md) | Unresolved, unvalidated commercial questions. |

Human retains authority over all irreversible actions (push, deploy, merge,
publish, delete, spend, external comms, secrets/production, scope changes).

---

## Public Overview - For Architects & Recruiters

### The Problem DogBuild Addresses

AI agents can implement and review work. Without a durable control plane, the human becomes the message bus:

- Implementation agent completes work → human copies result to reviewer
- Reviewer provides findings → human carries feedback back to implementer
- Every round of fixes requires manual relay

**DogBuild explores how intent, authority, evidence, routing, and handoffs can become deterministic and auditable.**

### Architecture

DogBuild operates as a three-layer control plane:

1. **Authority Layer** — Documented governance rules and human authority model; mechanical verification pending #167/#176
2. **Evidence Layer** — All decisions append-only to GitHub, linked to exact commit SHAs (process in use)
3. **Routing Layer** — Deterministic routing rules documented; deterministic autonomous invocation pending #176

Coordination happens through:
- **Curated MCP portals** — Bounded, documented tool sets for each agent role
- **GitHub as source of truth** — Exact-head architecture for atomic decision snapshots
- **Async workflows** — No real-time agent-to-agent coupling

### Design Principles

1. **Human authority is explicit and auditable** — Every delegation has documented authority limits
2. **Coordination is deterministic** — Routing and escalation rules are verifiable, not ad-hoc
3. **Evidence is append-only** — No decision can be hidden or forgotten; all findings link to context
4. **Agents operate in isolation** — No hidden conversations; all coordination through verified state
5. **Failures are intentional** — When uncertainty exceeds authority, the system interrupts the human

### Current Status (September 2026)

**Component Status Legend:**
- `DOCUMENTED` — design and approach are recorded; working usage may be ahead of documentation
- `PROCESS_IN_USE` — live, being used for this task, but may not be widely adopted or fully tested
- `DESIGN_REVIEWED` — design decisions and principles settled; implementation status varies
- `LIVE_ENFORCEMENT_PENDING` — designed and reviewed; full mechanical enforcement awaits separate work
- `IMPLEMENTED / NOT DEPLOYED` — code exists and is merged; not yet active in production
- `IN_REVIEW` — under independent verification; findings may require rework
- `PLANNED` — designed or sketched; implementation not yet started
- `DEFERRED` — identified and scoped; safety findings defer admission

**Core Components:**
- Project state ledger: `DOCUMENTED / PROCESS_IN_USE` (all decisions tracked in GitHub)
- Authority model: `DOCUMENTED / PROCESS_IN_USE (mechanical enforcement PENDING)` per #167/#176
- Tool portal (53 MCP tools): `DOCUMENTED / DESIGN_REVIEWED / LIVE_ENFORCEMENT_PENDING` per #169
- Exact-SHA CI aggregation: `IN_REVIEW` per #175/PR #184

### Roadmap

**Current Wave (MVP / Dogfood)**
- [x] File-based project state ledger
- [x] Authority model definition and documentation
- [x] MCP portal connectivity and inventory documentation
- [ ] Curation enforcement and least-privilege access control (#169, #167)
- [ ] Automated agent-to-agent coordination (requires #183, #185 in progress)

**Next Wave (If Demand Validates)**
- [ ] Real-time decision routing without human relay
- [ ] Multi-agent orchestration across implementation and review
- [ ] Production-grade audit logging and compliance
- [ ] Integration with existing development workflows

### For the Curious

- **Vision & constraints:** [`vision.md`](vision.md)
- **Authority model:** [`docs/authority-model.md`](docs/authority-model.md)
- **Governance boundaries:** [`docs/governance-boundaries.md`](docs/governance-boundaries.md)
- **Product governance snapshot:** [`docs/product-governance-source.md`](docs/product-governance-source.md)
- **Commercial assumptions (unvalidated):** [`docs/commercial-assumptions.md`](docs/commercial-assumptions.md)

---

## Project Status & Links

- 🔧 **Active Development:** DogBuild is under active development and is not yet production-ready
- 📋 **Live Dogfooding:** Tests run in CI on every push (see [CI workflow](.github/workflows/ci.yml))
- 🔗 **Evidence:** Every status claim above links to its GitHub issue or PR
