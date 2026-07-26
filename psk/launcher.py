"""DogBuild launcher — branded entry point that recovers state and starts Claude Code.

`dogbuild start` detects the repository, verifies DogBuild initialization, reads
persistent state, displays a branded banner, ensures the Claude skill is current,
and launches Claude Code with a continuation instruction and safe permission mode.

Uses os.execvp (no unsafe shell invocation). No dangerously-skip-permissions.
Process exec replaces the launcher so terminal I/O stays clean.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from . import (brief as brief_mod, gitutil, identity as identity_mod,
               install as install_mod, store)
from .errors import StateNotFoundError


# Permission modes Claude Code accepts. We default to acceptEdits.
_SAFE_MODES = frozenset({"default", "manual", "acceptEdits", "plan", "auto"})
_DANGEROUS_MODES = frozenset({"bypassPermissions", "dontAsk"})
DEFAULT_PERMISSION_MODE = "acceptEdits"


def find_claude() -> Optional[str]:
    """Return the path to the `claude` executable, or None."""
    return shutil.which("claude")


def detect_repo(path: str) -> str:
    """Resolve the Git repository root for *path*.

    Raises NotAGitRepoError if *path* is not inside a git work tree.
    """
    return gitutil.repo_root(path)


def verify_initialized(root: str) -> None:
    """Raise StateNotFoundError if DogBuild is not initialized in *root*."""
    store.load_state(root)  # raises StateNotFoundError


def recover_state(root: str) -> dict:
    """Build the state recovery dict used for the banner and Claude instruction.

    Returns a dict with keys matching `dogbuild where-am-i --json` output.
    """
    fields, warnings = brief_mod.build(root)
    return {
        "project": fields["product"],
        "stage": fields["current_milestone"],
        "current_milestone": fields["current_milestone"],
        "exact_next_action": fields["exact_next_action"],
        "current_verified_state": fields["current_verified_state"],
        "human_decision_needed": fields["human_decision_needed"],
        "human_decision_reason": fields.get("human_decision_reason", ""),
        "goal_alignment": fields["goal_alignment"],
        "active_agent": fields.get("active_agent"),
        "warnings": warnings,
    }


def _try_recover_goal_contract(root: str) -> dict:
    """Load goal contract fields, returning an empty dict on failure."""
    try:
        state = store.load_state(root)
        gc = state.goal_contract
        if gc:
            return {
                "revision": gc.get("revision"),
                "product_name": gc.get("product_name"),
            }
    except Exception:
        pass
    return {}


def _try_recover_autonomy(root: str) -> dict:
    """Load autonomy status, returning an empty dict on failure."""
    try:
        from . import autonomy as autonomy_mod
        st = autonomy_mod.status(root)
        return {
            "autonomy_status": st["status"],
            "instruction_epoch": st["instruction_epoch"],
        }
    except Exception:
        return {}


def render_banner(state: dict) -> str:
    """Render the branded DogBuild status banner."""
    lines = [
        "",
        "DogBuild>",
        "",
        f"  Project:            {state['project']}",
        f"  Stage:              {state['stage']}",
        f"  Current milestone:  {state['current_milestone']}",
        f"  Last verified:      {state['current_verified_state']}",
        f"  Exact next action:  {state['exact_next_action']}",
        f"  Human needed:       {state['human_decision_needed']}"
        + (f" — {state['human_decision_reason']}" if state['human_decision_reason'] else ""),
        "",
    ]
    if state.get("warnings"):
        for w in state["warnings"]:
            lines.append(f"  Warning: {w}")
        lines.append("")
    return "\n".join(lines)


def build_startup_instruction(state: dict, root: str) -> str:
    """Build the concise initial instruction for Claude Code."""
    gc = _try_recover_goal_contract(root)
    au = _try_recover_autonomy(root)

    parts = [
        "DogBuild is active for this repository.",
        "",
        "Recover the current project from live Git evidence and persistent DogBuild state.",
        "",
        "Use the latest verified evidence.",
        "Follow the active Goal Contract.",
        "Prioritize the shortest path to the agreed deliverable.",
        "Do not add optional features; park them.",
        'Answer "What\'s happening?" in short plain English.',
        "State queries must not interrupt active work.",
        "Continue approved routine work without asking unnecessary questions.",
        "Stop for destructive, external, paid, secret-related, production, or material goal-changing actions.",
        "Human authority remains supreme.",
        "",
        f"Project: {state['project']}",
        f"Stage: {state['stage']}",
        f"Current milestone: {state['current_milestone']}",
        f"Exact next action: {state['exact_next_action']}",
    ]

    if gc.get("revision") is not None:
        parts.append(f"Goal Contract revision: {gc['revision']}")
    if au.get("autonomy_status"):
        parts.append(f"Autonomy: {au['autonomy_status']}")
    if au.get("instruction_epoch") is not None:
        parts.append(f"Instruction epoch: {au['instruction_epoch']}")

    parts.append(f"Human needed: {state['human_decision_needed']}")

    return "\n".join(parts)


def ensure_skill(dry_run: bool = False) -> dict:
    """Install or refresh the DogBuild Claude skill if needed.

    Returns the install result dict.
    """
    return install_mod.install_claude_skill(dry_run=dry_run)


def build_claude_args(
    prompt: str,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
) -> List[str]:
    """Build the argument list for the Claude Code process."""
    return [
        "claude",
        prompt,
        "--permission-mode",
        permission_mode,
    ]


def validate_permission_mode(mode: str) -> str:
    """Validate and return the permission mode, raising ValueError for dangerous modes."""
    if mode in _DANGEROUS_MODES:
        raise ValueError(
            f"Permission mode '{mode}' is not allowed by DogBuild safety policy. "
            f"Use one of: {', '.join(sorted(_SAFE_MODES))}"
        )
    if mode not in _SAFE_MODES:
        raise ValueError(
            f"Unknown permission mode '{mode}'. "
            f"Use one of: {', '.join(sorted(_SAFE_MODES))}"
        )
    return mode


def start(
    path: str = ".",
    *,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    dry_run: bool = False,
) -> dict:
    """Full start sequence. Returns a result dict.

    In normal mode, this function does NOT return — it execs Claude Code.
    In dry-run mode, it returns the full diagnostic dict.
    """
    # 1. Validate permission mode
    permission_mode = validate_permission_mode(permission_mode)

    # 2. Detect repository
    root = detect_repo(path)

    # 3. Verify initialized
    verify_initialized(root)

    # 4. Refresh live Git evidence (already done by recover_state → brief.build)
    # 5. Recover state and build banner
    state = recover_state(root)

    # 6. Ensure skill is current
    skill_result = ensure_skill(dry_run=dry_run)

    # 7. Build startup instruction
    instruction = build_startup_instruction(state, root)

    # 8. Find Claude
    claude_path = find_claude()

    # 9. Build argument list
    args = build_claude_args(instruction, permission_mode)

    # 10. Render banner
    banner = render_banner(state)

    result = {
        "root": root,
        "project": state["project"],
        "state": state,
        "banner": banner,
        "permission_mode": permission_mode,
        "claude_executable": claude_path,
        "instruction": instruction,
        "args": args,
        "skill": skill_result,
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    # Not a dry run — actually launch
    if not claude_path:
        print("error: Claude Code is not installed or not on PATH.\n"
              "Install it from https://docs.anthropic.com/en/docs/claude-code\n"
              "or ensure the 'claude' command is available.",
              file=sys.stderr)
        sys.exit(1)

    # Print banner
    print(banner)
    print("  Starting Claude execution agent…\n")

    # Exec Claude — replaces this process
    os.execvp(claude_path, args)
    # Never reached
