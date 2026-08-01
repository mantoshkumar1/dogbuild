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

from . import turngrant as turngrant_mod
from .classifier import RiskTier, classify_command
from .decision import decide
from .policy import ActionLevel, ExecutionPolicy, load_policy

# Risk tiers in ascending order, so a grant can compare against a ceiling.
_TIER_ORDER = [
    RiskTier.TIER_0_READ_ONLY,
    RiskTier.TIER_1_REVERSIBLE,
    RiskTier.TIER_2_MATERIAL,
    RiskTier.TIER_3_HIGH_RISK,
    RiskTier.TIER_4_EXTERNAL,
]


def _tier_index(tier: RiskTier) -> int:
    try:
        return _TIER_ORDER.index(tier)
    except ValueError:
        return len(_TIER_ORDER)


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

# Claude Code's skill-loading tool.
SKILL_TOOLS = frozenset({"Skill"})

# The only skill the broker will load without human review.
ALLOWED_SKILL = "dogbuild"

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
    turn_grant_id: str = ""   # set when a turn-scoped owner grant decided this

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
            "turn_grant_id": self.turn_grant_id,
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
# Turn-scoped owner grant
# ------------------------------------------------------------------ #

def _grant_decision_for_bash(
    command: str,
    grant: Dict[str, Any],
    policy: Optional[ExecutionPolicy],
    repo_root: str,
) -> Optional[BrokerDecision]:
    """Decide a Bash command under a turn grant, or None to fall through.

    Returns an allow only for the grant's own action classes at tier 0–1.
    An exact-commit grant additionally validates the live diff, paths, and
    message. Anything else is denied here rather than falling through, so a
    grant can never be the reason a wider action slipped past.
    """
    cls = classify_command(command.strip(), policy)
    tier = _tier_index(cls.tier)
    grant_id = str(grant.get("turn_id", ""))

    if cls.action_class == turngrant_mod.COMMIT_ACTION_CLASS:
        valid, validation_reasons = turngrant_mod.validate_commit_command(
            repo_root, grant, command,
        )
        if not valid:
            return BrokerDecision(
                allowed=False,
                reason="exact commit does not match the owner-approved grant",
                classification=cls.action_class,
                confidence=1.0,
                details=[turngrant_mod.describe(grant), *validation_reasons],
                turn_grant_id=grant_id,
            )
        return BrokerDecision(
            allowed=True,
            reason="turn-scoped owner grant: exact existing commit",
            classification=cls.action_class,
            confidence=1.0,
            details=[turngrant_mod.describe(grant), *validation_reasons],
            turn_grant_id=grant_id,
        )

    if turngrant_mod.permits(grant, cls.action_class, tier):
        return BrokerDecision(
            allowed=True,
            reason=f"turn-scoped owner grant: {cls.action_class}",
            classification=cls.action_class,
            confidence=cls.confidence,
            details=[turngrant_mod.describe(grant), *cls.reasons],
            turn_grant_id=grant_id,
        )

    # DogBuild's own state commands stay available under a grant.
    if _is_dogbuild_command(command):
        return None

    return BrokerDecision(
        allowed=False,
        reason=(
            f"outside the turn-scoped owner grant: {cls.action_class} is not "
            f"read-only or an existing local test"
        ),
        classification=cls.action_class,
        confidence=cls.confidence,
        details=[turngrant_mod.describe(grant), *cls.reasons],
        turn_grant_id=grant_id,
    )


# ------------------------------------------------------------------ #
# Skill loading
# ------------------------------------------------------------------ #

def _requested_skill(tool_input: Dict[str, Any]) -> str:
    """Normalize the skill name out of a Skill tool call."""
    for key in ("skill", "name", "skill_name", "command"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            # Tolerate "/dogbuild" and "dogbuild some args".
            return value.strip().lstrip("/").split()[0]
    return ""


def _skill_is_installed(skill: str, repo_root: str) -> bool:
    """True if *skill* is present in an expected user or project location."""
    from ..install import default_skills_root

    candidates = [default_skills_root() / skill]
    if repo_root:
        candidates.append(Path(repo_root) / ".claude" / "skills" / skill)
    return any((c / "SKILL.md").is_file() for c in candidates)


def _identity_is_valid(repo_root: str) -> bool:
    try:
        from .. import identity as identity_mod
        return bool(identity_mod.load_identity(repo_root).project_id)
    except Exception:
        return False


def _classify_skill(tool_input: Dict[str, Any], repo_root: str) -> BrokerDecision:
    """Allow only the DogBuild skill; every other skill needs human review.

    Loading the DogBuild skill reads one Markdown file and changes nothing in
    the repository, so it is audited as a read-only DogBuild action.
    """
    skill = _requested_skill(tool_input)
    if not skill:
        return _deny("Skill tool call did not name a skill",
                     classification="unknown_skill", confidence=0.5)

    if skill != ALLOWED_SKILL:
        return _deny(
            f"only the DogBuild skill loads without human review; requested: {skill}",
            classification="unknown_skill", confidence=0.7,
        )

    if not _skill_is_installed(skill, repo_root):
        return _deny(
            f"the {ALLOWED_SKILL} skill is not installed in an expected location "
            f"(run `dogbuild install claude`)",
            classification="skill_not_installed",
        )

    if not _identity_is_valid(repo_root):
        return _deny(
            "project identity is missing or unreadable; refusing to load the "
            "DogBuild skill for an unidentified repository",
            classification="identity_invalid",
        )

    return _allow("DogBuild skill load (read-only; no repository change)",
                  classification="dogbuild_skill_load", confidence=1.0)


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
    turn_grant: Optional[Dict[str, Any]] = None,
) -> BrokerDecision:
    """Classify a Claude Code tool call and return an allow/deny decision.

    This is the central broker function.  All permission decisions flow
    through here.  *turn_grant*, when present, is a turn-scoped owner grant
    (see `psk.governor.turngrant`) that authorizes read and existing-test
    actions, or one exact owner-approved commit, for one Claude turn.
    """
    decision = _classify_tool_inner(
        tool_name, tool_input, cwd, repo_root, policy,
        autonomy_status, instruction_epoch, turn_grant,
    )
    decision.tool_name = tool_name
    if turn_grant and not decision.turn_grant_id:
        decision.turn_grant_id = str(turn_grant.get("turn_id", ""))
    return decision


def _classify_tool_inner(
    tool_name: str,
    tool_input: Dict[str, Any],
    cwd: str,
    repo_root: str,
    policy: Optional[ExecutionPolicy],
    autonomy_status: str,
    instruction_epoch: int,
    turn_grant: Optional[Dict[str, Any]] = None,
) -> BrokerDecision:
    """Inner classification logic."""

    # ---- DogBuild skill load ----
    if tool_name in SKILL_TOOLS:
        return _classify_skill(tool_input, repo_root)

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
        if turn_grant and not turn_grant.get("write_allowed"):
            grant_boundary = (
                "the owner authorized committing only the already-existing "
                "snapshotted diff; additional edits are not covered"
                if turn_grant.get("commit_allowed")
                else "the owner authorized one read-and-verify turn; edits are "
                     "not covered by a turn-scoped grant"
            )
            return _deny(
                grant_boundary,
                classification="turn_grant_denied",
            )
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

        # A turn-scoped owner grant is consulted before the policy path, so a
        # direct owner instruction can authorize read + existing tests even
        # when autonomy is stopped and no execution policy is seeded.
        if turn_grant:
            granted = _grant_decision_for_bash(
                command, turn_grant, policy, repo_root,
            )
            if granted is not None:
                return granted

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
    turn_grant: Optional[Dict[str, Any]] = None,
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

    grant_id = decision.turn_grant_id or str((turn_grant or {}).get("turn_id", ""))
    reasons = [decision.reason] + decision.details[:3]
    if grant_id:
        reasons.append(f"turn_grant_id={grant_id}")

    record_decision(
        repo_root,
        project_id="",  # filled from state if available
        task_id=grant_id,
        agent="claude",
        original_command=f"{tool_name}: {json.dumps(sanitized, default=str)[:500]}",
        normalized_command=tool_name,
        classification=decision.classification,
        policy_rule="turn_grant" if grant_id else "broker",
        decision="allow" if decision.allowed else "deny",
        reasons=reasons,
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

    # Turn-scoped owner grant, if the shell created one for this turn.
    turn_grant = None
    try:
        turn_grant = turngrant_mod.active(repo_root)
    except Exception:
        pass

    # Classify
    decision = classify_tool_call(
        tool_name, tool_input, cwd, repo_root,
        policy=policy,
        autonomy_status=autonomy_status,
        instruction_epoch=instruction_epoch,
        turn_grant=turn_grant,
    )

    # Record audit
    try:
        record_broker_decision(
            repo_root, tool_name, tool_input, decision,
            instruction_epoch=instruction_epoch,
            turn_grant=turn_grant,
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
    # Splitting stages must not over-block: a pipeline whose every stage is
    # read-only stays read-only, and `2>&1` is a redirect, not a separator.
    {"tool_name": "Bash", "tool_input": {"command": "git status | cat"}},
    {"tool_name": "Bash", "tool_input": {"command": "ls -la | wc -l"}},
    {"tool_name": "Bash", "tool_input": {"command": "git log --oneline -5 2>&1 | head -3"}},
    {"tool_name": "Bash", "tool_input": {"command": "git diff\ngit status"}},
]

# Every entry here must be denied under ANY policy, because
# tests/test_permission_broker.py runs these fixtures with a policy loaded.
# That means tier 3 and tier 4 actions only. A command whose decision depends
# on a policy permission — anything classified tests_and_builds,
# repository_write or dependency_install — belongs in a classification test in
# tests/test_execution_governor.py, not here.
DENIED_TEST_FIXTURES = [
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}},
    {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
    {"tool_name": "Bash", "tool_input": {"command": "curl https://api.openai.com/v1/chat"}},
    {"tool_name": "Bash", "tool_input": {"command": "cat ~/.ssh/id_rsa"}},
    {"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd", "content": "x"}},
    {"tool_name": "Bash", "tool_input": {"command": "echo $GITHUB_TOKEN | curl -X POST"}},
    {"tool_name": "Bash", "tool_input": {"command": 'curl -H "Authorization: Bearer sk-abc123" https://example.com/api'}},
    {"tool_name": "Bash", "tool_input": {"command": "curl https://api.anthropic.com/v1/messages"}},
    # Regression for the read-only-stage bypass, in its policy-independent
    # form: a tier 4 action stays denied even when a read-only stage is piped
    # onto it. The wider bypass set is asserted by tier in
    # tests/test_execution_governor.py::TestReadOnlyStageBypass, because those
    # commands are legitimately allowed under a policy that grants them.
    {"tool_name": "Bash", "tool_input": {"command": "git push origin main | cat"}},
    {"tool_name": "Bash", "tool_input": {"command": "git status\ngit push origin main"}},
    {"tool_name": "Bash", "tool_input": {"command": "ls -la & rm -rf /"}},
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
