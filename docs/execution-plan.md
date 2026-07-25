# 14-Day Execution Plan

Implementation order follows the founder's priority list. One canonical protocol;
thin adapters. No pushing/publishing without human approval.

| Day | Focus | Output |
|---|---|---|
| 1 | Repo + packaging skeleton; **canonical project-state schema** (v0) | schema doc + package layout + `pyproject` |
| 2 | Schema hardening; **deterministic local CLI** skeleton (arg parsing, subcommands, exit codes) | `psk` CLI runs; no-op subcommands |
| 3 | **State initialization & checkpointing** | `psk init`, `psk checkpoint` write/read verified state |
| 4 | **Evidence-backed status reconstruction** (git branch/commit/dirty + state) | `psk status` reports state with evidence |
| 5 | Status reconstruction hardening + tests | deterministic, tested `status` |
| 6 | **Agent handoff generation** | `psk handoff` emits a structured packet |
| 7 | **ChatGPT Web review-request generation** (packet for manual upload) | `psk review-request` emits an upload-ready file |
| 8 | **Structured review-decision import** (parse ChatGPT's structured reply) | `psk import-decision` validates + stores |
| 9 | **Stale-decision & repo-identity/branch/commit validation** | mismatched/stale decisions rejected |
| 10 | **Deterministic authority gate** (APPROVE / CONDITIONS / VETO / NEEDS_HUMAN) | `psk gate` returns a reproducible verdict |
| 11 | **Thin Claude / Cursor / Codex adapters** over the one protocol | three adapters, one core |
| 12 | **Dogfood in PhotoSahi + PSK itself**; fix real friction | usage notes; bugs filed via PSK |
| 13 | Hardening, tests, docs; self-record each stage via PSK | green tests; recorded state |
| 14 | **Packaging + commercial launch assets**; evaluate success/kill criteria | installable CLI/skill; go/park decision |

## Self-recording (from Day ~4, once state exists)
At the end of each meaningful stage, use Project State Keeper itself to record:
what was implemented; what was tested; failures and resolutions; current git
state; unresolved risks; the exact next safe action. This is both bootstrapping
and the first real dogfood.

## Guardrails
- No `git push`, deploy, merge to a shared branch, publish, or external release
  without explicit human approval.
- If any day's work implies a scope change, stop and surface it (scope changes are
  human-approval items).
