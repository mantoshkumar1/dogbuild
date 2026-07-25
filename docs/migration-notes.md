# Migration Notes — from the Markdown-only workflow to canonical state

## Baseline preservation
- **No original "skill" baseline files were present in this repository** at Day 1,
  so nothing existing was deleted or rewritten. If a prior Markdown-only
  project-state skill exists elsewhere, **preserve those files** (copy them in
  unchanged) *before* integrating them — do not overwrite them.
- The lab's decision journal (`revenue-opportunity-lab`) is the closest existing
  Markdown-only precedent (hand-written `CURRENT_STATE.md`, `decision-log/`). It
  is **not** modified by this tool; PSK's canonical state is separate.

## Conceptual mapping (Markdown-only → canonical `.ai/` state)

| Markdown-only workflow | Canonical model (this tool) |
|---|---|
| A hand-written "current state" note | `.ai/state.json` (validated snapshot) + `.ai/STATE.md` (generated projection) |
| A running log of what happened | `.ai/events.jsonl` (append-only, typed events) |
| "We decided X" prose | `decisions{}` records with an explicit binding (repo/branch/commit/scope/action) |
| "Here's what I did / tested" prose | `checkpoints{}` records (implemented / tested / risks / next safe action) |
| Ad-hoc "TODO" items | `items{}` with a typed `status` |
| Trust the narration | `evidence{}` first-class records; git facts captured, not described |

## Retained behavior
- Human-readable Markdown remains available — but now **generated** from state
  (`STATE.md`), so it can't silently drift from the facts.
- History stays append-only and greppable.

## Superseded behavior
- Free-text "current state" notes as the source of truth are superseded by
  `state.json` (the projection is downstream, never authoritative).
- "We approved this" claims without context are superseded by decision **bindings**
  that record exactly which repo/branch/commit/scope/action an approval applies to
  (enables Day 9 staleness checks).

## Known compatibility limitations (Day 1)
- No importer yet for arbitrary legacy Markdown notes → canonical state (manual
  re-entry for now).
- The authority **gate** (evaluating decisions) is not implemented until Day 10;
  Day 1 only *records* decisions.
- scp-like SSH remotes (`git@host:path`) are stored as-is (they carry no secret);
  only URL-form credentials are stripped.
