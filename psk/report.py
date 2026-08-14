"""Write small, explicitly supplied DogBuild status reports.

Reports are deliberately narrow.  DogBuild does not copy project files, command
output, or state history into them: callers provide four concise, single-line
facts and choose the destination directory.  This makes the output suitable
for a shared status area without hard-coding a particular machine or repo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, Optional

from . import gitutil
from .errors import ValidationError


_MAX_FIELD_LENGTH = 280
_SECRET_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:Bearer|Authorization)\s+\S+", re.IGNORECASE),
)


def _safe_line(label: str, value: str) -> str:
    """Validate a short report field before it can be written to disk."""
    text = (value or "").strip()
    if not text:
        raise ValidationError(f"{label} is required")
    if "\n" in text or "\r" in text:
        raise ValidationError(f"{label} must be one line; do not paste logs or source code")
    if len(text) > _MAX_FIELD_LENGTH:
        raise ValidationError(f"{label} must be {_MAX_FIELD_LENGTH} characters or fewer")
    if "```" in text:
        raise ValidationError(f"{label} must not include a code block")
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise ValidationError(f"{label} appears to contain a secret; it was not written")
    return text


def _new_report_path(destination: Path, timestamp: datetime) -> Path:
    base = timestamp.strftime("%Y-%m-%dT%H%M%SZ") + "-summary"
    candidate = destination / f"{base}.md"
    suffix = 2
    while candidate.exists():
        candidate = destination / f"{base}-{suffix}.md"
        suffix += 1
    return candidate


def write_status_report(
    path: str,
    *,
    output_dir: str,
    changed: str,
    worked: str,
    blocked: str,
    next_action: str,
    now: Optional[datetime] = None,
) -> Dict[str, str]:
    """Write one safe status report and return its public metadata.

    ``output_dir`` is intentionally required.  DogBuild never assumes where a
    user keeps shared reports, and it never overwrites an existing report.
    """
    root = gitutil.repo_root(path)
    destination = Path(output_dir).expanduser().resolve()
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)

    fields = {
        "What changed": _safe_line("what changed", changed),
        "What worked": _safe_line("what worked", worked),
        "What is blocked": _safe_line("what is blocked", blocked),
        "What happens next": _safe_line("what happens next", next_action),
    }
    git = gitutil.capture_git_state(root)
    report_path = _new_report_path(destination, timestamp)
    destination.mkdir(parents=True, exist_ok=True)

    head = git["head_commit"][:12] if git["head_commit"] else "unborn"
    lines = [
        f"# DogBuild report — {timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"- Project: {Path(root).name}",
        f"- Branch: {git['branch']}",
        f"- Head: {head}",
        "",
    ]
    for heading, value in fields.items():
        lines.extend((f"## {heading}", value, ""))
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "report": str(report_path),
        "project": Path(root).name,
        "branch": git["branch"],
        "head": head,
    }
