# DogBuild Genesis Packet — revision 3 repository identity

The owner explicitly approved renaming the product repository from
`project-state-keeper` to `dogbuild` on 2026-07-28. This revision changes only
the repository identity. The product goal, milestone, constraints, acceptance
criteria, and next action remain unchanged.

```yaml
schema_version: 1
packet_type: project_genesis
project_name: DogBuild
core_repository: dogbuild
problem: Solo developers lose project purpose, current state, decisions, and context while moving work between ChatGPT, Claude, Codex, and multiple repositories.
target_user: Solo developers who explore projects in ChatGPT and implement them with Claude Code or Codex.
desired_outcome: Turn a mature AI discussion into an executable project contract, keep all agents aligned with it, verify repository evidence, and involve the human only for genuine exceptions.
why_now: The owner renamed the repository to match the established DogBuild product and command before outside-user testing.
current_milestone: Real use over several normal work sessions, then one outside-user installation test. The local control loop milestone is COMPLETE, proven end to end on PhotoSahi and closed on 2026-07-27.
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
exact_first_action: Use DogBuild normally for real work across several sessions and record what breaks or gets in the way. Build no new feature until that evidence exists.
created_by: codex
human_approved: true
```
