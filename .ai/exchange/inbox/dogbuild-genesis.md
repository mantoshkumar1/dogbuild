schema_version: 1
packet_type: project_genesis
project_name: DogBuild
core_repository: project-state-keeper
problem: Solo developers lose project purpose, current state, decisions, and context while moving work between ChatGPT, Claude, Codex, and multiple repositories.
target_user: Solo developers who explore projects in ChatGPT and implement them with Claude Code or Codex.
desired_outcome: Turn a mature AI discussion into an executable project contract, keep all agents aligned with it, verify repository evidence, and involve the human only for genuine exceptions.
why_now: The founder experiences this repeatedly while building PhotoSahi and DogBuild itself and currently acts as messenger, historian, and coordinator between AI tools.
current_milestone: Complete one short, reliable local control loop using ChatGPT as reviewer and Claude as executor.
acceptance_criteria:
  - The human can see where the project is in under 20 seconds.
  - A mature discussion can become an approved project contract.
  - Claude can continue without receiving the entire ChatGPT conversation.
  - Work remains bound to the active objective and milestone.
  - Optional ideas are parked rather than implemented.
  - The human is interrupted only when a real choice is required.
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
unresolved_assumptions:
  - external willingness to pay
  - final Lite versus Pro boundary
  - automatic cross-provider transport
parked_ideas:
  - project forecasting and analytics
  - BYOK model-cost optimization
  - premium reviewer with cheaper executor
  - automatic ChatGPT transport
exact_first_action: Make the Goal Contract and Orientation Brief reliably reflect the current approved DogBuild purpose.
created_by: chatgpt
human_approved: true
