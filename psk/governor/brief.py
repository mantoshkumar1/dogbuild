"""Agent-facing policy brief — generated from policy, not manually duplicated.

Produces a concise instruction block that can be given to Claude or Codex at
task start, describing what is automatically allowed, what requires approval,
and what is prohibited.
"""

from __future__ import annotations

from typing import List

from .policy import ActionLevel, ExecutionPolicy


def render_agent_brief(policy: ExecutionPolicy) -> str:
    """Generate the agent-facing policy brief from the execution policy."""
    auto: List[str] = []
    approval: List[str] = []
    denied: List[str] = []

    for action_class, level in sorted(policy.permissions.items()):
        label = action_class.replace("_", " ")
        if level == ActionLevel.AUTO:
            auto.append(label)
        elif level == ActionLevel.TASK_SCOPED:
            auto.append(f"{label} (within task scope)")
        elif level == ActionLevel.APPROVAL:
            approval.append(label)
        elif level == ActionLevel.DENY:
            denied.append(label)

    lines = [
        f"DogBuild execution policy for task: {policy.scope.task_id}",
        f"Project: {policy.scope.project_id}",
        f"Branch: {policy.scope.branch}",
        "",
    ]

    if auto:
        lines.append("Automatically allowed:")
        for item in auto:
            lines.append(f"  - {item}")
        lines.append("")

    if policy.boundaries.allowed_domains:
        lines.append("Approved domains:")
        for d in policy.boundaries.allowed_domains:
            lines.append(f"  - {d}")
        lines.append("")

    if policy.boundaries.allowed_write_roots:
        lines.append("Approved write locations:")
        for r in policy.boundaries.allowed_write_roots:
            lines.append(f"  - {r}")
        lines.append("")

    if approval:
        lines.append("Requires explicit approval:")
        for item in approval:
            lines.append(f"  - {item}")
        lines.append("")

    if denied:
        lines.append("Prohibited:")
        for item in denied:
            lines.append(f"  - {item}")
        lines.append("")

    lines.extend([
        "Use simple atomic commands.",
        "Do not combine directory fallback, network requests, and inspection in one command.",
    ])

    return "\n".join(lines)


def render_delta(policy: ExecutionPolicy, action_class: str) -> str:
    """Explain only the policy delta for an out-of-scope action.

    Instead of a long generic warning, this tells the user exactly what
    differs from the current policy.
    """
    level = policy.permission_for(action_class)
    label = action_class.replace("_", " ")

    if level == ActionLevel.DENY:
        return f"This action is prohibited: {label} is denied by the current policy."
    if level == ActionLevel.APPROVAL:
        return f"This action differs from the current policy because {label} requires approval."
    if level == ActionLevel.TASK_SCOPED:
        return (f"This action is allowed within the current task scope "
                f"({policy.scope.task_id}).")
    return f"This action is automatically allowed: {label}."
