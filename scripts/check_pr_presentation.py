#!/usr/bin/env python3
"""Validate DogBuild's reader-facing pull-request presentation contract.

The contract keeps the GitHub Project ledger issue-only while ensuring a PR
reader can still identify the authoritative issue, its status, the PR's role,
and whether the PR is partial or completes that work. The check is pure and
local; CI reads GitHub's already-provided event payload instead of calling the
GitHub API.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List


TOP_DIRECTIVE = re.compile(
    r"^(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s*:?\s*#(\d+)(?:\s+—.*)?$",
    re.IGNORECASE,
)
AUTHORITATIVE = re.compile(
    r"^\s*-\s+\*\*Authoritative issue:\*\*\s*#(\d+)\s+—\s*(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
PROJECT_RECORD = re.compile(
    r"^\s*-\s+\*\*Project record:\*\*\s*Issue #(\d+) in the configured GitHub Project\s+—\s+PR not a Project item\.\s*$",
    re.IGNORECASE | re.MULTILINE,
)
ROLE = re.compile(r"^\s*-\s+\*\*PR role:\*\*\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
SEMANTICS = re.compile(
    r"^\s*-\s+\*\*Closing semantics:\*\*\s*`?(partial slice|full completion)`?\s*;?",
    re.IGNORECASE | re.MULTILINE,
)


def findings(body: str) -> List[str]:
    """Return structural contract findings for a PR body, or an empty list."""
    first_line = body.split("\n", 1)[0].strip()
    directive = TOP_DIRECTIVE.fullmatch(first_line)
    if not directive:
        return [
            'PR presentation contract requires a plain top-of-body issue directive such as '
            '"Closes #123" or "Refs #123 — partial; issue remains open".'
        ]

    issue = directive.group(1)
    result: List[str] = []
    authoritative = AUTHORITATIVE.search(body)
    if not authoritative or authoritative.group(2).lower().startswith("current execution status"):
        result.append(
            'PR presentation contract requires "Authoritative issue: #<same issue> — '
            '<current execution status>".'
        )
    elif authoritative.group(1) != issue:
        result.append(
            f"PR presentation contract names #{authoritative.group(1)} as authoritative, "
            f"but the top-of-body directive names #{issue}."
        )

    project = PROJECT_RECORD.search(body)
    if not project:
        result.append(
            'PR presentation contract requires "Project record: Issue #<same issue> in the '
            'configured GitHub Project — PR not a Project item.".'
        )
    elif project.group(1) != issue:
        result.append(
            f"PR presentation contract Project record names #{project.group(1)}, "
            f"but the top-of-body directive names #{issue}."
        )

    role = ROLE.search(body)
    if not role or re.search(r"full implementation\s*/\s*partial slice", role.group(1), re.IGNORECASE):
        result.append("PR presentation contract requires a concrete PR role, not the template choices.")

    semantics = SEMANTICS.search(body)
    if not semantics:
        result.append('PR presentation contract requires closing semantics of exactly "partial slice" or "full completion".')
    else:
        expected = "partial slice" if first_line.lower().startswith("ref") else "full completion"
        if semantics.group(1).lower() != expected:
            result.append(
                f'PR presentation contract says "{semantics.group(1)}", '
                f'but the top-of-body directive requires "{expected}".'
            )
    return result


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} <github-event.json>", file=sys.stderr)
        return 2
    event = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    pull_request = event.get("pull_request")
    if pull_request is None:
        return 0
    result = findings(pull_request.get("body") or "")
    if not result:
        print("PR presentation contract is complete.")
        return 0
    print(f"Found {len(result)} PR presentation-contract finding(s):", file=sys.stderr)
    for finding in result:
        print(f"  - {finding}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
