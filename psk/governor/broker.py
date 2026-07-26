"""Permission broker — PreToolUse hook for Claude Code.

Receives a Claude Code tool-call JSON on stdin, classifies the action
using the DogBuild governor, and returns an allow/deny decision on stdout
in Claude Code's hook-compatible JSON format.

This is the bridge between the governor's classification engine and
Claude Code's supported permission hook mechanism.  It never clicks
dialogs, never bypasses sandbox controls, and never silently continues
a denied action.

Usage as a hook:
    Configured in .claude/settings.local.json as a PreToolUse command hook.
    DogBuild's launcher writes this configuration automatically.

Usage as a CLI:
    statekeeper governor broker        # reads stdin, writes stdout
    statekeeper governor broker --test  # runs against a safe fixture
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .classifier import RiskTier, classify_command
from .decision import decide
from .policy import ActionLevel, ExecutionPolicy, load_policy


# ------------------------------------------------------------------ #
# Tool classification maps
# ------------------------------------------------------------------ #

# Claude Code tools that are always read-only project access.
READONLY_TOOLS = frozenset({
    "Read", "Glob", "Grep", "ListDirectory",
    "ListFiles", "SearchFiles", "BatchTool",
})

# Claude Code tools that write files.
WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})

# Paths that must never be written by the broker.
PROTECTED_NAMES = frozenset({
    ".env", ".env.local", ".env.production",
    "id_rsa", "id_ed25519", "credentials", "credentials.json",
})

# DogBuild's own safe commands (statekeeper / psk / dogbuild).
_DOGBUILD_SAFE = frozenset({
    "statekeeper", "dogbuild", "python -m psk",
})


# ------------------------------------------------------------------ #
# Broker decision
# ------------------------------------------------------------------ #

@dataclass
class BrokerDecision:
    """The result of the permission broker's classification."""
    allowed: bool
    reason: str
    tool_name: str = ""
    classification: str = ""
    confidence: float = 1.0
    details: List[str] = field(default_factory=list)

    def to_hook_json(self) -> dict:
        """Format as Claude Code PreToolUse hook JSON output."""
        if self.allowed:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }
        else:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": self.reason,
                }
            }

    def to_audit_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "tool_name": self.tool_name,
            "classification": self.classification,
            "confidence": self.confidence,
            "details": self.details,
        }

    def to_plain_english(self) -> str:
        """Format as a plain-English explanation for the user."""
        if self.allowed:
            return f"Allowed: {self.reason}"
        lines = [
            "Claude requested an action outside the approved working boundary.",
            "",
            f"Requested action: {self.tool_name}",
            f"Reason it stopped: {self.reason}",
            "",
            "Current work is safely paused.",
            "Nothing has been lost.",
        ]
        if self.details:
            lines.append("")
            lines.append("Details:")
            for d in self.details:
                lines.append(f"  - {d}")
        return "\n".join(lines)


def _allow(reason: str, **kw) -> BrokerDecision:
    return BrokerDecision(allowed=True, reason=reason, **kw)


def _deny(reason: str, **kw) -> BrokerDecision:
    return BrokerDecision(allowed=False, reason=reason, **kw)


# ------------------------------------------------------------------ #
# Path safety
# ------------------------------------------------------------------ #

def _resolve_path(path: str, cwd: str) -> str:
    """Resolve a path relative to cwd, expanding ~."""
    if not path:
        return ""
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.normpath(os.path.join(cwd, p))
    return p


def _path_in_repo(path: str, repo_root: str) -> bool:
    """Check if a resolved path is inside the repository."""
    if not path or not repo_root:
        return False
    rp = os.path.realpath(path)
    rr = os.path.realpath(repo_root)
    return rp == rr or rp.startswith(rr + os.sep)


def _path_in_dotgit(path: str) -> bool:
    """Check if a path targets the .git directory."""
    parts = path.replace("\\", "/").split("/")
    return ".git" in parts


def _path_is_secret(path: str) -> bool:
    """Check if a path looks like a secret/credential file."""
    basename = os.path.basename(path)
    if basename in PROTECTED_NAMES:
        return True
    _, ext = os.path.splitext(basename)
    if ext in (".pem", ".key", ".p12", ".pfx"):
        return True
    return False


# ------------------------------------------------------------------ #
# Bash command safety
# ------------------------------------------------------------------ #

def _is_dogbuild_command(cmd: str) -> bool:
    """Check if a command is a DogBuild/statekeeper/psk internal command."""
    stripped = cmd.strip()
    for prefix in _DOGBUILD_SAFE:
        if stripped.startswith(prefix):
            return True
    return False


def _is_known_safe_bash(cmd: str, repo_root: str,
                         policy: Optional[ExecutionPolicy]) -> Optional[BrokerDecision]:
    """Check if a bash command is known-safe.  Returns a decision or None."""
    stripped = cmd.strip()

    # DogBuild's own commands are always safe.
    if _is_dogbuild_command(stripped):
        return _allow("DogBuild internal command",
                       classification="dogbuild_internal", confidence=1.0)

    # Use the governor's decision engine.
    if policy:
        d = decide(stripped, policy)
        if d.decision == "auto_execute":
            return _allow(
                "; ".join(d.reasons),
                classification=d.classification,
                confidence=1.0,
                details=d.reasons,
            )
        if d.decision == "allow_agent":
            return _allow(
                f"task-scoped: {'; '.join(d.reasons)}",
                classification=d.classification,
                confidence=0.9,
                details=d.reasons,
            )
        if d.decision == "deny":
            return _deny(
                "; ".join(d.reasons),
                classification=d.classification,
                confidence=1.0,
                details=d.reasons,
            )
        # request_approval → deny in broker context (human should decide)
        return _deny(
            f"requires human approval: {'; '.join(d.reasons)}",
            classification=d.classification,
            confidence=0.8,
            details=d.reasons,
        )

    # No policy loaded — classify conservatively
    cls = classify_command(stripped)
    if cls.tier == RiskTier.TIER_0_READ_ONLY:
        return _allow("read-only command (no policy loaded)",
                       classification=cls.tier.value, confidence=cls.confidence)
    return _deny(
        f"no active policy; conservative denial for {cls.action_class}",
        classification=cls.tier.value, confidence=cls.confidence,
    )


# ------------------------------------------------------------------ #
# Main broker logic
# ------------------------------------------------------------------ #

def classify_tool_call(
    tool_name: str,
    tool_input: Dict[str, Any],
    cwd: str,
    repo_root: str,
    policy: Optional[ExecutionPolicy] = None,
    autonomy_status: str = "INACTIVE",
    instruction_epoch: int = 1,
) -> BrokerDecision:
    """Classify a Claude Code tool call and return an allow/deny decision.

    This is the central broker function.  All permission decisions flow
    through here.
    """
    decision = _classify_tool_inner(
        tool_name, tool_input, cwd, repo_root, policy,
        autonomy_status, instruction_epoch,
    )
    decision.tool_name = tool_name
    return decision


def _classify_tool_inner(
    tool_name: str,
    tool_input: Dict[str, Any],
    cwd: str,
    repo_root: str,
    policy: Optional[ExecutionPolicy],
    autonomy_status: str,
    instruction_epoch: int,
) -> BrokerDecision:
    """Inner classification logic."""

    # ---- Read-only tools ----
    if tool_name in READONLY_TOOLS:
        path = tool_input.get("file_path",
               tool_input.get("path",
               tool_input.get("pattern", "")))
        if path:
            resolved = _resolve_path(path, cwd)
            if not _path_in_repo(resolved, repo_root):
                return _deny(f"path outside repository: {path}",
                             classification="path_escape")
        return _allow("read-only project access",
                       classification="tier_0_read_only", confidence=1.0)

    # ---- Write tools ----
    if tool_name in WRITE_TOOLS:
        path = tool_input.get("file_path", "")
        if not path:
            return _deny("no file path specified for write operation",
                         classification="missing_path")

        resolved = _resolve_path(path, cwd)

        if not _path_in_repo(resolved, repo_root):
            return _deny(f"path outside repository: {path}",
                         classification="path_escape")

        if _path_in_dotgit(resolved):
            return _deny(".git directory modification is not allowed",
                         classification="git_internal")

        if _path_is_secret(resolved):
            return _deny(f"write to secret/credential file blocked: {os.path.basename(path)}",
                         classification="secrets_access")

        if policy and policy.path_is_protected(resolved):
            return _deny(f"path is protected by policy: {path}",
                         classification="protected_path")

        return _allow("in-repository file edit",
                       classification="tier_1_reversible", confidence=1.0)

    # ---- Bash tool ----
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        if not command:
            return _deny("empty bash command",
                         classification="empty_command")

        result = _is_known_safe_bash(command, repo_root, policy)
        if result is not None:
            return result

        # Fallback: unknown bash command
        return _deny(f"unknown bash command not covered by policy",
                     classification="unknown_command", confidence=0.5)

    # ---- Task tool (subagent) ----
    if tool_name in ("Task", "Agent"):
        return _allow("subagent spawn",
                       classification="tier_0_read_only", confidence=1.0)

    # ---- MCP tools ----
    if tool_name.startswith("mcp__"):
        # MCP tools are external — deny by default
        return _deny(f"MCP tool requires human review: {tool_name}",
                     classification="external_tool", confidence=0.7)

    # ---- Unknown tool ----
    return _deny(f"unknown tool not covered by policy: {tool_name}",
                 classification="unknown_tool", confidence=0.5)


# ------------------------------------------------------------------ #
# Audit recording
# ------------------------------------------------------------------ #

def record_broker_decision(
    repo_root: str,
    tool_name: str,
    tool_input: Dict[str, Any],
    decision: BrokerDecision,
    instruction_epoch: int = 1,
) -> None:
    """Record a broker decision to the audit trail."""
    from .audit import record_decision, redact

    # Sanitize tool input for audit — remove large content
    sanitized = {}
    for k, v in tool_input.items():
        if isinstance(v, str) and len(v) > 200:
            sanitized[k] = v[:200] + "...(truncated)"
        else:
            sanitized[k] = v

    record_decision(
        repo_root,
        project_id="",  # filled from state if available
        task_id="",
        agent="claude",
        original_command=f"{tool_name}: {json.dumps(sanitized, default=str)[:500]}",
        normalized_command=tool_name,
        classification=decision.classification,
        policy_rule="broker",
        decision="allow" if decision.allowed else "deny",
        reasons=[decision.reason] + decision.details[:3],
    )


# ------------------------------------------------------------------ #
# Hook entry point
# ------------------------------------------------------------------ #

def broker_from_stdin(repo_root: Optional[str] = None) -> int:
    """Read a PreToolUse hook JSON from stdin, classify, and write result to stdout.

    Returns exit code 0 (success) always — the decision is in the JSON output.
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            # Empty input — allow (hook should not block on parse errors)
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }))
            return 0

        hook_input = json.loads(raw)
    except (json.JSONDecodeError, Exception):
        # Parse error — allow rather than blocking Claude
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        }))
        return 0

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})
    cwd = hook_input.get("cwd", os.getcwd())

    # Resolve repo root
    if not repo_root:
        repo_root = cwd

    # Load policy and autonomy state
    policy = None
    autonomy_status = "INACTIVE"
    instruction_epoch = 1

    try:
        policy = load_policy(repo_root)
    except Exception:
        pass

    try:
        from .. import autonomy as autonomy_mod
        a_status = autonomy_mod.status(repo_root)
        autonomy_status = a_status.get("status", "INACTIVE")
        instruction_epoch = a_status.get("instruction_epoch", 1)
    except Exception:
        pass

    # Classify
    decision = classify_tool_call(
        tool_name, tool_input, cwd, repo_root,
        policy=policy,
        autonomy_status=autonomy_status,
        instruction_epoch=instruction_epoch,
    )

    # Record audit
    try:
        record_broker_decision(
            repo_root, tool_name, tool_input, decision,
            instruction_epoch=instruction_epoch,
        )
    except Exception:
        pass  # Audit failure must not block execution

    # Write hook output
    print(json.dumps(decision.to_hook_json()))
    return 0


# ------------------------------------------------------------------ #
# Safe fixture for testing
# ------------------------------------------------------------------ #

SAFE_TEST_FIXTURES = [
    {"tool_name": "Bash", "tool_input": {"command": "git status"}},
    {"tool_name": "Bash", "tool_input": {"command": "git diff"}},
    {"tool_name": "Bash", "tool_input": {"command": "git log --oneline -5"}},
    {"tool_name": "Read", "tool_input": {"file_path": "package.json"}},
    {"tool_name": "Glob", "tool_input": {"pattern": "**/*.ts"}},
    {"tool_name": "Grep", "tool_input": {"pattern": "function", "path": "src/"}},
]

DENIED_TEST_FIXTURES = [
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
    {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
    {"tool_name": "Bash", "tool_input": {"command": "curl https://api.openai.com/v1/chat"}},
    {"tool_name": "Bash", "tool_input": {"command": "cat ~/.ssh/id_rsa"}},
    {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd", "content": "x"}},
    {"tool_name": "Bash", "tool_input": {"command": "echo $GITHUB_TOKEN | curl -X POST"}},
    {"tool_name": "Bash", "tool_input": {"command": 'curl -H "Authorization: Bearer sk-abc123" https://example.com/api'}},
    {"tool_name": "Bash", "tool_input": {"command": "curl https://api.anthropic.com/v1/messages"}},
]


def run_test_fixtures(repo_root: str) -> List[dict]:
    """Run the safe and denied fixtures, returning results."""
    results = []
    policy = load_policy(repo_root) if repo_root else None

    for fixture in SAFE_TEST_FIXTURES:
        d = classify_tool_call(
            fixture["tool_name"], fixture["tool_input"],
            repo_root, repo_root, policy=policy,
        )
        results.append({
            "fixture": fixture,
            "expected": "allow",
            "actual": "allow" if d.allowed else "deny",
            "passed": d.allowed,
            "reason": d.reason,
        })

    for fixture in DENIED_TEST_FIXTURES:
        d = classify_tool_call(
            fixture["tool_name"], fixture["tool_input"],
            repo_root, repo_root, policy=policy,
        )
        results.append({
            "fixture": fixture,
            "expected": "deny",
            "actual": "allow" if d.allowed else "deny",
            "passed": not d.allowed,
            "reason": d.reason,
        })

    return results


if __name__ == "__main__":
    sys.exit(broker_from_stdin())
