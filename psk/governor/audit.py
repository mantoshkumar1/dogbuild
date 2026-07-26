"""Audit trail — records every execution decision with redaction.

Append-only log at `.ai/execution_audit.jsonl`.  Sensitive data (tokens,
passwords, credentials, private keys) is redacted before writing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..util import canonical_json, new_uuid, now_iso


# Patterns to redact from logged commands and outputs.
_REDACT_PATTERNS = [
    # Environment variable assignments with secret-ish names
    re.compile(
        r"(AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|GITHUB_TOKEN|API_KEY|"
        r"DATABASE_URL|DB_PASSWORD|PRIVATE_KEY|SECRET_KEY|AUTH_TOKEN|"
        r"ACCESS_TOKEN|REFRESH_TOKEN|CLIENT_SECRET|OPENAI_API_KEY|"
        r"ANTHROPIC_API_KEY)\s*=\s*\S+",
        re.I,
    ),
    # Authorization headers (e.g. "Authorization: Bearer sk-abc123")
    re.compile(r"(Authorization|Bearer|Token)\s*[:=]\s*\S+(\s+\S+)?", re.I),
    # Inline passwords in URLs
    re.compile(r"://[^:]+:([^@]+)@"),
    # PEM/key file contents
    re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----.*?-----END", re.S),
    # Cookie values
    re.compile(r"(Cookie|Set-Cookie)\s*[:=]\s*\S+", re.I),
]

_REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Remove sensitive values from a string."""
    result = text
    for pat in _REDACT_PATTERNS:
        result = pat.sub(lambda m: m.group(0).split("=")[0] + "=" + _REDACTED
                         if "=" in m.group(0)
                         else _REDACTED,
                         result)
    return result


@dataclass
class AuditRecord:
    """One execution decision record."""
    record_id: str
    timestamp: str
    project_id: str
    task_id: str
    agent: str
    original_command: str
    normalized_command: str
    classification: str
    policy_rule: str
    decision: str
    reasons: List[str]
    user_approved: Optional[bool] = None
    execution_outcome: Optional[str] = None
    files_affected: List[str] = field(default_factory=list)
    exit_code: Optional[int] = None
    rejection_reason: str = ""
    rollback_info: str = ""

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "agent": self.agent,
            "original_command": redact(self.original_command),
            "normalized_command": redact(self.normalized_command),
            "classification": self.classification,
            "policy_rule": self.policy_rule,
            "decision": self.decision,
            "reasons": self.reasons,
            "user_approved": self.user_approved,
            "execution_outcome": self.execution_outcome,
            "files_affected": self.files_affected,
            "exit_code": self.exit_code,
            "rejection_reason": self.rejection_reason,
            "rollback_info": self.rollback_info,
        }


AUDIT_FILE = "execution_audit.jsonl"


def audit_path(repo_root: str) -> Path:
    from .. import store
    return store.ai_dir(repo_root) / AUDIT_FILE


def record_decision(
    repo_root: str,
    *,
    project_id: str,
    task_id: str,
    agent: str,
    original_command: str,
    normalized_command: str,
    classification: str,
    policy_rule: str,
    decision: str,
    reasons: List[str],
    user_approved: Optional[bool] = None,
    execution_outcome: Optional[str] = None,
    files_affected: Optional[List[str]] = None,
    exit_code: Optional[int] = None,
    rejection_reason: str = "",
) -> AuditRecord:
    """Append an audit record.  Redacts sensitive data before writing."""
    rec = AuditRecord(
        record_id=new_uuid(),
        timestamp=now_iso(),
        project_id=project_id,
        task_id=task_id,
        agent=agent,
        original_command=original_command,
        normalized_command=normalized_command,
        classification=classification,
        policy_rule=policy_rule,
        decision=decision,
        reasons=reasons,
        user_approved=user_approved,
        execution_outcome=execution_outcome,
        files_affected=list(files_affected or []),
        exit_code=exit_code,
        rejection_reason=rejection_reason,
    )
    p = audit_path(repo_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(canonical_json(rec.to_dict()) + "\n")
    return rec


def read_audit(repo_root: str) -> List[dict]:
    """Read all audit records."""
    p = audit_path(repo_root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
