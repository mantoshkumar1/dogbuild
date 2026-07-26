"""DogBuild launcher — branded entry point that recovers state and starts Claude Code.

`dogbuild start` detects the repository, verifies DogBuild initialization, reads
persistent state, displays a branded banner, ensures the Claude skill is current,
and launches Claude Code with a continuation instruction and safe permission mode.

Uses os.execvp (no unsafe shell invocation). No dangerously-skip-permissions.
Process exec replaces the launcher so terminal I/O stays clean.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import (brief as brief_mod, gitutil, identity as identity_mod,
               install as install_mod, store)
from .errors import StateNotFoundError


# Permission modes Claude Code accepts. We default to acceptEdits.
_SAFE_MODES = frozenset({"default", "manual", "acceptEdits", "plan", "auto"})
_DANGEROUS_MODES = frozenset({"bypassPermissions", "dontAsk"})
DEFAULT_PERMISSION_MODE = "acceptEdits"


# ------------------------------------------------------------------ #
# Hook configuration for Claude Code PreToolUse
# ------------------------------------------------------------------ #

def _find_psk_root() -> str:
    """Find the root of the psk package (parent of psk/)."""
    return str(Path(__file__).resolve().parent.parent)


def build_hook_command() -> str:
    """Build the shell command for the PreToolUse hook.

    Uses PYTHONPATH so the hook subprocess can import psk.governor.broker
    regardless of where Claude Code runs it from.
    """
    psk_root = _find_psk_root()
    return f"PYTHONPATH={psk_root} python3 -m psk.governor.broker"


def build_hooks_config() -> Dict[str, Any]:
    """Build the hooks section for .claude/settings.local.json."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "type": "command",
                    "command": build_hook_command(),
                }
            ]
        }
    }


def write_hooks_config(repo_root: str, *, dry_run: bool = False) -> Dict[str, Any]:
    """Write the PreToolUse hook config to .claude/settings.local.json.

    Merges with any existing settings rather than overwriting the whole file.
    Returns the written config dict.
    """
    settings_dir = Path(repo_root) / ".claude"
    settings_file = settings_dir / "settings.local.json"

    hooks_config = build_hooks_config()

    # Load existing settings if present
    existing = {}
    if settings_file.exists():
        try:
            existing = json.loads(settings_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Merge hooks into existing config
    existing["hooks"] = hooks_config["hooks"]

    if not dry_run:
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file.write_text(
            json.dumps(existing, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return existing


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
    raw_claude: bool = False,
    dry_run: bool = False,
) -> dict:
    """Full start sequence. Returns a result dict.

    In normal mode, this function does NOT return — it execs Claude Code.
    In dry-run mode, it returns the full diagnostic dict.

    If *raw_claude* is True, skip DogBuild hook installation and launch
    Claude Code with its native permission mode (no governor broker).
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

    # 11. Install permission broker hook (unless --raw-claude)
    hooks_config = None
    if not raw_claude:
        hooks_config = write_hooks_config(root, dry_run=dry_run)

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
        "hooks": hooks_config,
        "raw_claude": raw_claude,
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
    if raw_claude:
        print("  Starting Claude (raw mode — no DogBuild governor)…\n")
    else:
        print("  Starting Claude with DogBuild governor…\n")

    # Set PYTHONPATH so hook subprocess can import psk
    psk_root = _find_psk_root()
    env_path = os.environ.get("PYTHONPATH", "")
    if psk_root not in env_path:
        os.environ["PYTHONPATH"] = (
            f"{psk_root}:{env_path}" if env_path else psk_root
        )

    # Exec Claude — replaces this process
    os.execvp(claude_path, args)
    # Never reached
