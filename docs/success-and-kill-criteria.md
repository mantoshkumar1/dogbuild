# Success & Kill Criteria

## MVP success (the tool works — a *usefulness* test, not a market test)
- I **actually use it daily** across **≥2 real projects** (PhotoSahi + PSK itself)
  through the two-week window.
- It reliably prevents a concrete class of cross-agent failures: **lost
  decisions, duplicated work, acting on stale approvals, silent overrides.**
- The **manual ChatGPT file-exchange loop costs me less** than reconstructing and
  re-explaining context by hand.
- The **deterministic gate never** lets an execution agent proceed past a `VETO`,
  a stale/invalid decision, or outside approved scope.
- **No human-only action is ever auto-performed** (push/deploy/merge/publish/
  delete/spend/external comms/secrets/scope change).

## Kill / park criteria (personal tool)
Park the build if, after the two weeks:
- I **don't reach for it**, or it adds more overhead than it removes;
- the manual file-exchange loop is **too tedious to sustain**;
- the core coordination problem **isn't actually solved** (agents still drift
  despite the ledger);
- the gate produces **non-deterministic or untrustworthy** verdicts I can't rely
  on.

## Commercial evaluation (LATER — after dogfood proves usefulness)
This is a **separate** gate, deliberately deferred. Do **not** treat MVP success
as commercial validation.
- **Continue toward selling** only if, after packaging, **unrelated users show
  real willingness to pay** (not praise — payment or a credible pre-commit).
- **Park as a personal utility** if the commercial evidence is weak. Parking is a
  legitimate, recorded outcome — not a failure.

See [`commercial-assumptions.md`](commercial-assumptions.md) for what remains
unproven.
