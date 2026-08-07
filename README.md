# DogBuild

A local, file-based **project interface and authority layer** between coding agents
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
- DogBuild's product activation and commercial constraints originated in the
  private Revenue Opportunity Lab. DogBuild owns its implementation and runtime
  truth. See [`docs/governance-boundaries.md`](docs/governance-boundaries.md) and
  the versioned [`docs/product-governance-source.md`](docs/product-governance-source.md)
  snapshot.

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
