# DogBuild — First-Run Walkthrough (Quickstart)

Run the whole DogBuild control loop once, on a throwaway repository, in a few
minutes: install → initialize → import an approved Genesis → orient → request a
review → gate an approved decision → perform one exact action → checkpoint.

This walkthrough uses a **deterministic demo decision** (a hand-authored fixture)
so it runs fully offline with no reviewer in the loop. See
[Demo decision vs. real reviewer decision](#demo-decision-vs-real-reviewer-decision).

## Prerequisites

- Python ≥ 3.9 and Git.
- `pip` with `setuptools ≥ 61` (the build backend this package pins). A current
  Python toolchain already satisfies this.
- No network is required to run the loop itself; only installing the package
  needs your existing local toolchain.

## Install (isolated virtual environment)

```bash
# from anywhere; point pip at your local Project State Keeper checkout
python3 -m venv .venv && . .venv/bin/activate
pip install /path/to/project-state-keeper
statekeeper --version
```

## Walkthrough

```bash
# 1. A disposable project with one commit
mkdir /tmp/dogbuild-first-run && cd /tmp/dogbuild-first-run
git init -q && git commit -q --allow-empty -m "init: empty demo repo"

# 2. Initialize DogBuild state (.ai/) + persistent identity
statekeeper init --name "Demo Notes" --objective "Prove the DogBuild loop on a throwaway repo"

# 3. Import a small, human-approved Genesis Packet (see below) -> Goal Contract + scope
statekeeper genesis import genesis-packet.md

# 4. Orient: where am I, what's next (target: understandable in < 20s)
statekeeper where-am-i

# 5. Record a working-agent declaration (an agent CLAIM, compared against git)
statekeeper declare \
  --building "Demo Notes: prove the loop" \
  --changed "Imported genesis; goal + scope set" \
  --verified "init + genesis import OK; where-am-i coherent" \
  --incomplete "review -> gate -> README -> checkpoint" \
  --next "Request review for a one-sentence README" \
  --actor claude --alignment IN_SCOPE --goal-rev 1

# 6. Request review for ONE tiny, reversible action
statekeeper review request \
  --question "May I create a one-sentence README describing the demo project?" \
  --action "Create a README containing one sentence describing the demo project." \
  --recommendation "Approve: tiny, reversible, matches the genesis exact_first_action." \
  --evidence "init + genesis import succeeded; active scope = milestone rev1."

# 7. Import a decision, then evaluate the gate
statekeeper review import .ai/exchange/demo-decision.md   # see fixture note below
statekeeper review gate                                   # expect: PROCEED

# 8. Perform ONLY the approved action, then checkpoint
echo "Demo Notes is a throwaway project used to prove the DogBuild local review loop end to end." > README.md
python -c "import psk.core as c; c.create_checkpoint('.', 'Approved one-sentence README created after PROCEED gate', actor='claude')"

# 9. Orient again — the loop is closed
statekeeper where-am-i
```

### The Genesis Packet (`genesis-packet.md`)

A Genesis Packet is a mature idea turned into an explicit contract. Import is
refused unless `human_approved: true` — an AI may never silently activate a
project. Minimal example:

```yaml
schema_version: 1
packet_type: project_genesis
project_name: Demo Notes
core_repository: dogbuild-first-run
problem: A solo developer needs a tiny demo project to prove the DogBuild loop.
target_user: A first-time DogBuild user evaluating the local review loop.
desired_outcome: Show the full loop on a throwaway repo.
current_milestone: Complete one reviewed, approved, checkpointed action on the demo repo.
exact_first_action: Add a one-sentence README describing the demo project.
created_by: chatgpt
human_approved: true
```

## Expected important outputs

- `init` → `Initialized .ai/ state and identity (project Demo Notes, id …)`.
- `genesis import` → `Imported project genesis: Demo Notes (goal rev 1, fingerprint …)`.
- `where-am-i` → a one-screen card: product, milestone, what just completed,
  verified git state, exact next action, gate, and **Human decision needed: yes/no**.
- `review gate` → `Result: PROCEED` with `Approved action: …` and the reminder
  that it authorizes *only* the exact approved action.
- After the checkpoint, `where-am-i` shows the approved action as “what just
  completed”; the now-consumed decision reads as `STOP_STATE_CHANGED`
  (historical, non-blocking) — expected once state has moved past it.

## Demo decision vs. real reviewer decision

The `review import` step above consumes a **deterministic demo decision**: a
hand-authored `review_decision` file whose binding fields (policy id/version/
fingerprint, goal id/revision/fingerprint, reviewed branch/head, scope) are
copied from the generated request packet, with `decision: APPROVE`. It is
labelled `DETERMINISTIC DEMO FIXTURE` in its rationale. It proves the
import → gate → action → checkpoint machinery **without** claiming a reviewer
looked at anything. The real ChatGPT review path was already proven separately.

A **real reviewer decision** is identical in format but produced by a reviewer,
not by you. To use one instead of the fixture:

1. `statekeeper review request …` writes a packet to
   `.ai/exchange/outbox/<packet-id>-chatgpt-review.md`.
2. Give that packet to the reviewer:
   - **ChatGPT Web / desktop:** upload the file and say “Review the attached
     Project State Keeper packet.” Copy ChatGPT’s reply — it already follows the
     required `review_decision` format — into a local file.
   - **A future supported API transport:** the same packet in, the same
     `review_decision` out; only the courier changes.
3. `statekeeper review import <that-file>` then `statekeeper review gate`.

Transport is deliberately manual: DogBuild does not automate browser or API
courier steps. The packet format is the stable contract; the courier is swappable.
