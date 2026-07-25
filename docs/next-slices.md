# Next slices (recorded, NOT yet implemented)

Day 3 shipped the first complete vertical slice: **one repo, one execution agent
(Claude), one ChatGPT review, one imported `APPROVE`, one gated `PROCEED`, one
checkpointed result** — manual Markdown transport, protocol kept agent-neutral.

The immediate next two slices, in order:

## Slice 1 — remaining decision outcomes
Add `VETO`, `APPROVE_WITH_CONDITIONS`, and `NEEDS_HUMAN` to the import + gate:
- `VETO` → gate `STOP`, present the compact conflict report; interrupt the human.
- `APPROVE_WITH_CONDITIONS` → gate proceeds only after each condition becomes a
  tracked requirement; stop if a condition can't be met or changes scope.
- `NEEDS_HUMAN` → gate stops, one focused question with choices + consequences.
- Plus: stale/superseded refresh and the local-agent-disagreement loop (challenge
  only with new evidence, re-request, stop until re-decided).

## Slice 2 — Claude → Codex handoff over the same canonical protocol
Add a second execution agent (Codex) using the **same** identity-carrying packets
and gate — no protocol redesign. Proves agent-neutrality end to end.

Everything else (Cursor support, Claude plugin packaging, browser automation,
OpenAI API, daemon, hosted backend, dashboard, payments, marketplace) remains out
of scope until these two slices land and the tool has been dogfooded repeatedly.
