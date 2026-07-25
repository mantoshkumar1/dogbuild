# Orientation Brief (specification — RESERVED, not yet implemented)

Answers, for the **human owner**, in under 20 seconds:
**Where am I, what am I building, what just happened, and what happens next?**

> Principle: *project state must be understandable to the human owner in seconds,
> not only machine-readable by agents.* Not implemented during the Day 3 acceptance
> (implementing it would change HEAD and invalidate an outstanding review).

## Reserved commands
```bash
statekeeper brief
statekeeper where-am-i
```
(may initially be aliases of each other.)

## Output (short; target reading time < 20s)
```text
Project:
Original objective:
Current phase:
What just completed:
Current verified state:
What is waiting:
Exact next action:
Why that action is next:
Human decision needed: yes/no
```

## Sources it must combine
1. live repository evidence;
2. canonical Project State Keeper state;
3. the latest working-agent declaration;
4. the latest valid ChatGPT decision;
5. the original user objective.

## Truth hierarchy (highest first)
```text
Live repository evidence
> valid imported decisions
> canonical Project State Keeper state
> latest agent declaration
> older chat summaries
```
If these conflict, the brief must **show the conflict**, not silently merge them.

## Working-agent declaration (input #3)
After every meaningful execution stage, Claude or Codex must provide a compact
declaration — **an agent claim, not canonical truth** (PSK must compare it against
git + verification evidence):
```text
What are we building?
What did I change?
What did I actually verify?
What failed and how was it resolved?
What remains incomplete?
What is the exact next safe action?
```

## Not in this slice
No automatic ChatGPT transport, browser automation, or OpenAI API. The Orientation
Brief is the next capability *after* the versioned-reviewer-policy slice; it is
recorded here, not built yet.
