# DogBuild personal alpha

DogBuild ships two views of the same project state.

## Technical view

```bash
dogbuild where-am-i          # one-screen CLI orientation
dogbuild where-am-i --json   # machine-readable
statekeeper where-am-i       # identical — `statekeeper` and `dogbuild` are the same command
```

## Human view

Open a fresh Claude session in the repository and ask:

> "What's happening?"

Claude identifies the repository, reads persistent DogBuild state, verifies live
Git evidence once, and answers in short plain English: the current stage, what
just completed, the exact next step, and whether you need to make a decision — no
pasted conversation history required.

## Install the Claude skill

```bash
dogbuild install claude            # installs to ~/.claude/skills/dogbuild/
dogbuild install claude --dry-run  # show what would change; write nothing
```

The installer is offline, idempotent, preserves unrelated files, and prints the
exact path it changed. Set `CLAUDE_SKILLS_DIR` to install elsewhere.
