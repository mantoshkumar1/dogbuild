# DogBuild Genesis Packet — revision 2 (control loop complete; next milestone is real use)

Provenance: the owner set this milestone in writing on 2026-07-27, approving the
closeout slice:

> "This slice is **APPROVED**: the real-terminal alpha worked, 383 tests pass,
> routine verification ran without permission prompts, the grant expired
> correctly, and no PhotoSahi files changed. … Do not begin another feature. The
> next milestone, after closeout, is real use over several normal work sessions
> and then one outside-user installation test."

What changes in this revision: **only `current_milestone` and
`exact_first_action`.** The product name, problem, target user, desired outcome,
and exclusions carry over from revision 1 unchanged. Revision 1 is preserved in
the event log and in `.ai/exchange/archive/genesis/`; nothing is rewritten.

Why milestone rev 1 is complete: it was "Complete one short, reliable local
control loop using ChatGPT as reviewer and Claude as executor." That loop now
runs end to end and has been exercised on a real repository — persistent
`dogBuild>` interface in a real terminal, state recovered across sessions, local
state queries answered without invoking Claude, Claude-backed execution under a
turn-scoped owner grant with the governor enforcing permissions, ChatGPT review
round-trip (manual transport) with conditions imported, satisfied, and closed,
and the PhotoSahi ledger reconciled and adopted at 0a36116 with no product
change. 390 tests green.

The next milestone is deliberately not a feature. It is evidence: does this hold
up under ordinary use, and can anyone but its author install it.

```yaml
packet_type: project_genesis
schema_version: 1
human_approved: true
created_by: owner
project_name: DogBuild
core_repository: project-state-keeper
problem: Solo developers lose project purpose, current state, decisions, and context while moving work between ChatGPT, Claude, Codex, and multiple repositories.
target_user: Solo developers who explore projects in ChatGPT and implement them with Claude Code or Codex.
desired_outcome: Turn a mature AI discussion into an executable project contract, keep all agents aligned with it, verify repository evidence, and involve the human only for genuine exceptions.
why_now: The local control loop is complete and proven on a real repository. What is unproven is whether it survives ordinary use and whether anyone else can install it.
current_milestone: Real use over several normal work sessions, then one outside-user installation test. The local control loop milestone (revision 1) is COMPLETE, proven end to end on PhotoSahi and closed on 2026-07-27.
exact_first_action: Use DogBuild normally for real work across several sessions and record what breaks or gets in the way. Build no new feature until that evidence exists.
acceptance_criteria:
- DogBuild is used for real work across several ordinary sessions without the owner falling back to raw Claude Code
- friction, breakage, and workarounds are recorded as they happen rather than reconstructed afterwards
- one person other than the owner installs DogBuild from the repository and reaches a working dogBuild> prompt
- the outside-user installation test is written up honestly, including whatever failed
explicit_exclusions:
- automatic browser control
- OpenAI API integration
- Anthropic API integration
- dashboards
- forecasting
- marketplace packaging
- payments
- Cursor support
- production deployment
- new features before the real-use evidence exists
unresolved_assumptions:
- that ordinary use will surface problems the built acceptance tests did not
- that an outside user can install DogBuild without the owner present
parked_ideas: []
```
