## DogBuild — Product Objective

> **Enable one person to run a large, evolving software project through multiple AI agents without losing project intent, decisions, context, execution state, or authority.**

DogBuild is not just a task manager or shared memory. It is the **coordination and control layer** between the human, the planning AI, execution AIs, and the codebase.

---

## Milestone 1 — Authoritative Project State

**Objective:** DogBuild can represent the current truth of one project.

It must capture:

- why the project exists,
- current product direction,
- repositories and branches,
- active objectives,
- settled constraints,
- important decisions,
- completed work,
- unresolved questions,
- immediate next actions.

At this stage, the state may still be maintained partly manually.

**Success condition:**

A new AI agent can enter the project and accurately explain:

> What is this project, where are we now, what has already been decided, and what should happen next?

---

## Milestone 2 — Reliable Agent Handoffs

**Objective:** One AI can complete work and hand it to another without you reconstructing the context.

The handoff should contain:

- assigned objective,
- boundaries and prohibited changes,
- relevant decisions,
- files changed,
- tests performed,
- problems discovered,
- unfinished work,
- recommended next action.

Example:

> Claude implements a feature. Codex receives the implementation state, reviews it, and knows exactly what Claude did and what remains.

**Success condition:**

You no longer need to manually explain the same task repeatedly across ChatGPT, Claude, Codex, and Cursor.

---

## Milestone 3 — Evolving Objectives and Work Graph

**Objective:** DogBuild can model real project evolution rather than a fixed checklist.

It must support:

- objectives splitting into sub-objectives,
- newly discovered tasks,
- dependencies,
- blockers,
- deferred work,
- cancelled work,
- experiments,
- parallel workstreams,
- unknown future work.

A task can produce another task. An objective can change after learning something new.

**Success condition:**

DogBuild preserves the project structure even when the original plan becomes obsolete.

---

## Milestone 4 — Decision Memory

**Objective:** Preserve not only what was decided, but why.

Every significant decision should include:

- decision,
- rationale,
- alternatives considered,
- evidence available at the time,
- status: provisional, accepted, rejected, or superseded,
- consequences,
- related tasks and files.

Example:

> PhotoSahi must preserve the original image because the authority evaluates the submitted original, not a generated replacement.

An agent must not casually reverse that decision later.

**Success condition:**

Agents stop repeating old debates or undoing intentional design choices.

---

## Milestone 5 — Authority and Delegation

**Objective:** DogBuild understands that different actors have different powers.

Suggested authority:

1. **Human owner** — final authority.
2. **Planning/review AI** — architecture, prioritization, decomposition and final review.
3. **Execution AI agents** — implementation within assigned boundaries.
4. **DogBuild** — records state, detects violations and controls handoffs.

The expensive AI should make high-value decisions. Lower-cost agents should perform bounded execution.

**Success condition:**

An execution agent cannot silently redefine project direction or expand scope without escalation.

---

## Milestone 6 — Automatic Repository Awareness

**Objective:** DogBuild derives execution state from the repository rather than depending entirely on written updates.

It should understand:

- current repository,
- branch and commit,
- modified files,
- recent commits,
- test results,
- uncommitted work,
- linked objective,
- whether work happened in the wrong project.

**Success condition:**

DogBuild can detect:

> The agent claims the feature is complete, but tests are failing and two files remain uncommitted.

---

## Milestone 7 — Contradiction and Drift Detection

**Objective:** Detect when proposed work conflicts with project truth.

Examples:

- modifying the wrong repository,
- reversing an accepted decision,
- duplicating completed work,
- implementing a cancelled requirement,
- expanding beyond assigned scope,
- marking work complete without evidence,
- two agents changing the same area incompatibly.

DogBuild should not automatically resolve every conflict. It should surface it to the appropriate authority.

**Success condition:**

DogBuild prevents expensive rework before conflicting changes are merged.

---

## Milestone 8 — Parallel Agent Coordination

**Objective:** Multiple execution agents can work simultaneously without you manually coordinating them.

DogBuild should:

- assign bounded work,
- identify dependencies,
- reserve overlapping areas,
- track agent ownership,
- merge discoveries into shared state,
- identify conflicts early,
- determine which work is ready for review.

**Success condition:**

Claude and Codex can work on separate tasks in the same project without repeatedly asking you what the other agent is doing.

---

## Milestone 9 — Project History and Reconstruction

**Objective:** DogBuild can explain how the project reached its current state.

It should answer:

- Why does this architecture exist?
- When did this objective change?
- Which experiment failed?
- Why was this feature postponed?
- What caused the last regression?
- Which decisions remain provisional?
- What was believed three months ago versus now?

**Success condition:**

You can return to the project after several months without reading every chat, commit and document.

---

## Milestone 10 — Cost-Aware AI Orchestration

**Objective:** Use the right AI for the right type of work.

DogBuild should distinguish between:

- architecture and strategic reasoning,
- implementation,
- test generation,
- code review,
- documentation,
- repetitive fixes,
- deep debugging.

It could recommend:

> Use the premium reasoning model for this architectural decision.  
> Use the cheaper execution agent for these seven mechanical changes.

**Success condition:**

The project receives high-quality reasoning without spending premium-model capacity on routine implementation.

---

## Milestone 11 — Local-First Solo Product

**Objective:** Make DogBuild usable by an individual developer without organizational infrastructure.

Initial product characteristics:

- local repository integration,
- no mandatory cloud account,
- project data remains local,
- CLI or editor integration,
- works with existing AI tools,
- minimal configuration,
- no requirement for a team to adopt it.

**Success condition:**

Another solo developer can install DogBuild and use it on a real project within 15 minutes.

---

## Milestone 12 — External Product Validation

**Objective:** Determine whether DogBuild solves a problem beyond your own workflow.

Validation should answer:

- Do other multi-agent developers lose project state?
- Which failure hurts most: wrong project, stale context, bad handoff, or decision drift?
- Do they use DogBuild repeatedly?
- Does it save measurable time?
- Will they pay?
- Do they prefer one-time pricing or subscription?

**Success condition:**

At least a small number of external users use it repeatedly without your direct supervision.

---

# Practical Delivery Sequence

Do not attempt all twelve milestones simultaneously.

### Version 0.1 — Project truth

- project identity,
- current state,
- decisions,
- active objective,
- next action.

### Version 0.2 — Handoffs

- generate agent briefing,
- record agent result,
- update shared state.

### Version 0.3 — Repository evidence

- branch,
- commit,
- changed files,
- tests,
- worktree status.

### Version 0.4 — Evolving work graph

- objectives,
- tasks,
- dependencies,
- discoveries,
- blocked and deferred work.

### Version 0.5 — Drift detection

- contradictions,
- stale instructions,
- wrong repository,
- scope violations.

### Version 1.0 — Solo multi-agent control system

A single developer can plan, delegate, execute, review and evolve a complex project across multiple AI agents without manually carrying the entire state in their head.

The defining test for DogBuild is:

> **Can you stop acting as the messenger between AIs while still remaining fully in control of the project?**
