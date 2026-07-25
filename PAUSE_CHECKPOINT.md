# PAUSE CHECKPOINT — Project State Keeper

Implementation is **temporarily paused** to preserve and strengthen the parent
governance system (Revenue Opportunity Lab) before continuing. This file makes it
possible to resume **without reconstructing the originating conversation.**

## Classification
```yaml
build_type: dogfood-first
build_number: 001
product_name: Project State Keeper   # do NOT rename
commercial_status: unvalidated
founder_problem_status: validated
implementation_status: active-but-temporarily-paused-for-governance-sync
parent_system: revenue-opportunity-lab   # ~/Desktop/project/revenue-opportunity-lab
```

## Git state (verified)
- **Branch:** `main`
- **HEAD:** `d283a20` (Dogfood: record Day 1 checkpoint via PSK itself)
- **Worktree:** clean before this checkpoint file was added.
- **Commits:** `f325692` scaffold → `a84e2d1` Day 1 impl → `d283a20` Day 1 dogfood.

## Repository tree (tracked at pause)
```
.ai/{STATE.md,events.jsonl,state.json}   # PSK's own dogfood state
PRODUCT.md  README.md  pyproject.toml  .gitignore
docs/{authority-model,mvp-scope,execution-plan,success-and-kill-criteria,commercial-assumptions,migration-notes}.md
psk/{__init__,__main__,core,errors,gitutil,models,projection,store,util,validation}.py
psk/schemas/{state,event}.schema.json
tests/{__init__,_helpers,test_util,test_gitutil,test_store_and_models,test_projection,test_core}.py
```

## Specifications completed
PRODUCT (dogfood→commercial path, Lite vs Pro), authority-model (**corrected
hierarchy: Human > ChatGPT > execution agents > State Keeper**), mvp-scope,
execution-plan (14 days), success-and-kill-criteria, commercial-assumptions (all
UNVALIDATED), migration-notes.

## Implementation completed (Day 1)
Canonical `.ai/` schema (v1.0.0); `state.json` + append-only `events.jsonl` +
deterministic `STATE.md`; repo identity (persistent UUID); git state + dirty
SHA-256 fingerprint; sanitized remotes; versioned objective/scope; item status
model; first-class evidence; decision records with staleness binding; reserved
human-only approvals; checkpoint model; JSON schemas; typed models; validation +
atomic safe-init serialization; minimal `psk init`/`psk show` CLI. **26 unittest
tests green.** PSK dogfooded on its own repo.

## Implementation NOT yet started
Day 2 CLI skeleton · Day 6 handoff generation · Day 7 ChatGPT review-request
packet · Day 8 decision import · Day 9 stale/identity validation · Day 10
deterministic authority gate · Day 11 thin Claude/Cursor/Codex adapters · Day 12
dogfood in PhotoSahi · Day 13 hardening · Day 14 packaging + commercial-assets/
go-or-park decision.

## Open design decisions
- Legacy Markdown → canonical-state importer (not built).
- Review-packet and decision-import file formats (Day 7–8).
- Deterministic gate rule set (Day 10).
- Thin-adapter interface shape (one protocol, three adapters).
- Where the original skill package lands inside this repo once imported.

## Day 1 intended scope (for the record — all delivered)
`.ai/` dir model; state.json; events.jsonl; repo identity + UUID; git state +
dirty fingerprint; versioned objective/scope; requested-item status; first-class
evidence; human/reviewer decision records; reserved human-only approvals;
checkpoint model; JSON Schemas; typed Python models; validation & serialization;
safe init; deterministic Markdown projection; tests; migration notes.

## Original skill package — baseline import STILL PENDING
The original working skill package (below) is **not present on the filesystem**
and has **not** been imported into this repo. Do not fabricate its contents or a
checksum. Import it (immutably) before building on it:
```
project-state-keeper/  (original skill)
├── SKILL.md
├── README.md
├── scripts/init-project-state.sh
├── assets/{PROJECT_STATE.template.md,DECISIONS.template.md,HANDOFF.template.md}
└── references/example-mobile-visual-state.md
```
It maintained `.ai/PROJECT_STATE.md`, `.ai/DECISIONS.md`, `.ai/HANDOFF.md`.

## Exact next safe action on resume
**Day 2:** implement the deterministic local CLI skeleton (argparse subcommands
with stable exit codes) over the existing `psk.core` API; add CLI-level tests.

## Prohibited actions (unchanged)
**No push. No publish. No deploy. No marketplace submission.** Irreversible/
external actions remain human-approved.
