# ChatGPT Web — Project Genesis prompt

When the user says: **"Turn this conversation into a DogBuild project,"** produce a
concise **Genesis Packet** for the user to review and approve. Do not invent facts;
summarize only what the conversation actually established. The human must approve it
before it becomes active — you may set `human_approved: false` and let the human
change it, or leave approval to the human.

Output exactly this YAML (fill every field; use `[]` for empty lists):

```yaml
schema_version: 1
packet_type: project_genesis
project_name: DogBuild
core_repository: dogbuild
problem: <the specific problem, one sentence>
target_user: <the specific user>
desired_outcome: <what success looks like>
why_now: <why this matters now>
current_milestone: <the single next milestone>
acceptance_criteria:
  - <observable criterion>
explicit_exclusions:
  - <what is deliberately out of scope>
unresolved_assumptions:
  - <what is still unproven>
parked_ideas:
  - <useful but out-of-scope idea>
exact_first_action: <the exact first implementation action>
created_by: chatgpt
human_approved: true
```

Rules:
- Keep it short and honest — a contract, not a pitch.
- Do not include commercial claims; demand/payment/distribution stay unvalidated.
- `human_approved: true` means the human has explicitly agreed. DogBuild
  will **refuse to import** a packet that is not `human_approved: true`.
- The user saves this to a file and runs: `statekeeper genesis import <file>`.
- Do not attempt to read the local repository or transport the file yourself — the
  human saves and imports it.
