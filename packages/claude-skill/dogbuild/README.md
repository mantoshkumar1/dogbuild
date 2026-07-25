# DogBuild — canonical Claude skill

The single maintained source for the DogBuild Claude skill lives inside the
Python package so that `dogbuild install claude` works after a normal
`pip install` (no repository checkout required):

    psk/skills/dogbuild/SKILL.md

Edit that file to change the skill. Install or update it into your user-level
Claude skills directory with:

    dogbuild install claude            # installs to ~/.claude/skills/dogbuild/
    dogbuild install claude --dry-run  # show what would change, write nothing

The installer is offline, idempotent, preserves unrelated files, and prints the
exact path it changed.
