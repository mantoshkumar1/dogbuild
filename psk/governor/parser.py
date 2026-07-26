"""Conservative shell command parser.

Splits compound commands into atomic actions, preserving quoted strings and
URLs.  When parsing confidence is low, refuses to auto-approve.  Returns
a normalized execution plan.

This is NOT a full Bash parser.  It handles the common patterns that agents
produce (semicolons, &&, ||, pipes) and flags uncertainty when it encounters
constructs it cannot safely split.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class AtomicAction:
    """One atomic command extracted from a compound shell expression."""
    command: str
    description: str = ""
    original_index: int = 0


@dataclass
class NormalizedPlan:
    """The result of parsing and normalizing a compound command."""
    original: str
    actions: List[AtomicAction] = field(default_factory=list)
    confidence: float = 1.0
    warnings: List[str] = field(default_factory=list)


# Characters/patterns that indicate compound commands.
_COMPOUND_SPLIT = re.compile(
    r"""
    (?:;|\s*&&\s*|\s*\|\|\s*)  # semicolon, &&, ||
    """,
    re.VERBOSE,
)

# Detect pipes (excluding || which is already handled).
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")

# Detect subshells.
_SUBSHELL = re.compile(r"\$\(|`")

# Detect redirections.
_REDIRECT = re.compile(r"[12]?>>?|<<")


def _describe_action(cmd: str) -> str:
    """Generate a human-readable description of a command."""
    cmd = cmd.strip()
    if not cmd:
        return "(empty)"

    if cmd.startswith("cd "):
        target = cmd[3:].strip().rstrip("/")
        # Detect fallback patterns like "2>/dev/null"
        target = re.sub(r"\s*2>/dev/null\s*", "", target).strip()
        return f"change directory to {target}" if target else "change directory"

    if re.match(r"^curl\b", cmd):
        url_match = re.search(r'https?://[^\s"\']+', cmd)
        output_match = re.search(r'-o\s+["\']?([^\s"\']+)', cmd)
        parts = []
        if url_match:
            parts.append(f"fetch {url_match.group(0)}")
        else:
            parts.append("network request")
        if output_match:
            parts.append(f"save to {output_match.group(1)}")
        return "; ".join(parts) if parts else "curl request"

    if re.match(r"^(ls|dir)\b", cmd):
        return f"list files: {cmd}"

    if cmd == "pwd":
        return "report working directory"

    if re.match(r"^git\s+", cmd):
        return f"git operation: {cmd}"

    if re.match(r"^(cat|head|tail|less|more)\b", cmd):
        return f"read file: {cmd}"

    if re.match(r"^(rm|rmdir)\b", cmd):
        return f"delete: {cmd}"

    if re.match(r"^(npm|pip|yarn|apt|brew)\b", cmd):
        return f"package manager: {cmd}"

    return cmd


def parse_compound(command: str) -> NormalizedPlan:
    """Parse a compound shell command into atomic actions.

    Returns a NormalizedPlan with individual actions, confidence level,
    and any warnings about unparseable constructs.
    """
    plan = NormalizedPlan(original=command)
    cmd = command.strip()

    if not cmd:
        plan.confidence = 1.0
        return plan

    warnings: List[str] = []

    # Check for constructs that reduce confidence.
    if _SUBSHELL.search(cmd):
        warnings.append("contains subshell expression — cannot fully parse")
        plan.confidence = min(plan.confidence, 0.3)

    if _PIPE.search(cmd):
        # Check for pipe-into-shell specifically
        if re.search(r"\|\s*(?:ba)?sh\b", cmd):
            warnings.append("pipes into shell — high risk")
            plan.confidence = min(plan.confidence, 0.1)
        else:
            warnings.append("contains pipe — treating as single action")
            plan.confidence = min(plan.confidence, 0.6)

    # Split on ;, &&, ||
    # First, protect quoted strings and URLs by tokenizing
    parts = _safe_split(cmd)

    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        action = AtomicAction(
            command=part,
            description=_describe_action(part),
            original_index=i,
        )
        plan.actions.append(action)

    if not plan.actions:
        plan.actions.append(AtomicAction(
            command=cmd,
            description=_describe_action(cmd),
        ))

    plan.warnings = warnings
    return plan


def _safe_split(cmd: str) -> List[str]:
    """Split a command on ;, &&, || while respecting quotes.

    This is a simplified splitter that handles common agent-produced patterns.
    """
    parts: List[str] = []
    current: List[str] = []
    in_single = False
    in_double = False
    i = 0

    while i < len(cmd):
        c = cmd[i]

        if c == "'" and not in_double:
            in_single = not in_single
            current.append(c)
            i += 1
            continue

        if c == '"' and not in_single:
            in_double = not in_double
            current.append(c)
            i += 1
            continue

        if in_single or in_double:
            current.append(c)
            i += 1
            continue

        # Check for && or ||
        if i + 1 < len(cmd):
            two = cmd[i:i+2]
            if two == "&&" or two == "||":
                parts.append("".join(current))
                current = []
                i += 2
                continue

        # Check for ;
        if c == ";":
            parts.append("".join(current))
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    if current:
        parts.append("".join(current))

    return parts


def normalize_for_policy(
    plan: NormalizedPlan,
    approved_scratch_dir: Optional[str] = None,
) -> NormalizedPlan:
    """Apply normalizations to make a plan safer.

    - Replace directory fallback patterns with the known approved directory.
    - Remove redundant diagnostic commands when safe.
    """
    if not approved_scratch_dir:
        return plan

    new_actions: List[AtomicAction] = []
    skip_cd = False

    for action in plan.actions:
        cmd = action.command.strip()

        # Detect cd-fallback pattern: "cd /X 2>/dev/null" (followed by || cd /tmp)
        if re.match(r"^cd\s+.+\s*2>/dev/null\s*$", cmd):
            skip_cd = True
            continue

        if skip_cd and re.match(r"^cd\s+/tmp\s*$", cmd):
            skip_cd = False
            # Replace both cd commands with one to the approved dir
            new_actions.append(AtomicAction(
                command=f"cd {approved_scratch_dir}",
                description=f"use approved scratch directory {approved_scratch_dir}",
            ))
            continue

        skip_cd = False

        # Normalize output paths in curl to use the approved scratch dir
        if re.match(r"^curl\b", cmd):
            output_match = re.search(r'-o\s+["\']?([^\s"\']+)', cmd)
            if output_match:
                old_path = output_match.group(1)
                if old_path.startswith("/tmp/") or old_path.startswith("/private/tmp/"):
                    import os.path
                    filename = os.path.basename(old_path)
                    new_path = f"{approved_scratch_dir}/{filename}"
                    cmd = cmd.replace(old_path, new_path)
                    action = AtomicAction(
                        command=cmd,
                        description=_describe_action(cmd),
                        original_index=action.original_index,
                    )

        new_actions.append(action)

    result = NormalizedPlan(
        original=plan.original,
        actions=new_actions,
        confidence=plan.confidence,
        warnings=list(plan.warnings),
    )
    return result
