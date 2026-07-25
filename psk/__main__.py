"""Minimal Day-1 entrypoint.

Only what Day 1 needs: `init` (safe initialization) and `show` (deterministic
projection). The full deterministic CLI surface is Day 2 (see
docs/execution-plan.md); this stub deliberately stays small.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, core, store
from .errors import PSKError


def _cmd_init(args) -> int:
    state = core.initialize(args.path, objective=args.objective, force=args.force)
    print(f"Initialized .ai/ state (psk id {state.identity.psk_uuid}) at {state.identity.root}")
    return 0


def _cmd_show(args) -> int:
    from . import gitutil
    from .projection import render_markdown
    repo = gitutil.repo_root(args.path)
    state = store.load_state(repo)
    print(render_markdown(state), end="")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="psk", description="Project State Keeper (Day 1)")
    parser.add_argument("--version", action="version", version=f"psk {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="initialize .ai/ state in a git repo")
    p_init.add_argument("path", nargs="?", default=".")
    p_init.add_argument("--objective", default=None)
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    p_show = sub.add_parser("show", help="print the Markdown projection of state")
    p_show.add_argument("path", nargs="?", default=".")
    p_show.set_defaults(func=_cmd_show)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PSKError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
