"""Stable CLI exit codes. Documented and tested; values may be refined but must
stay stable once released."""

from __future__ import annotations

SUCCESS = 0
INVALID_USAGE = 2        # argparse also uses 2
NO_REPOSITORY = 10       # not inside a git work tree
NOT_INITIALIZED = 11     # git repo, but Project State Keeper not initialized here
AMBIGUOUS_CONTEXT = 12   # two or more projects plausible -> stop, ask
PROJECT_MISMATCH = 13    # decision/handoff belongs to a different repo/project
MALFORMED_STATE = 14     # state/identity/decision malformed or incompatible
INTERNAL_ERROR = 20
