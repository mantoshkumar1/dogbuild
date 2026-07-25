"""Install the canonical DogBuild Claude skill into the user-level skills dir.

Offline, idempotent, and non-destructive: it only writes files under
`<skills-root>/dogbuild/`, never touching other skills or unrelated user files.
No network, no secrets. Supports a dry run.
"""

from __future__ import annotations

import filecmp
import os
import shutil
from pathlib import Path

from .errors import ValidationError

SKILL_NAME = "dogbuild"


def source_dir() -> Path:
    """The canonical skill source bundled inside the installed package."""
    return Path(__file__).resolve().parent / "skills" / SKILL_NAME


def default_skills_root() -> Path:
    """User-level Claude skills directory (override with CLAUDE_SKILLS_DIR)."""
    override = os.environ.get("CLAUDE_SKILLS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude" / "skills"


def install_claude_skill(skills_root=None, *, dry_run: bool = False) -> dict:
    src = source_dir()
    if not src.is_dir() or not (src / "SKILL.md").is_file():
        raise ValidationError(
            f"canonical skill source not found at {src} (package data missing)"
        )
    root = Path(skills_root).expanduser() if skills_root else default_skills_root()
    dest = root / SKILL_NAME

    src_files = sorted(p for p in src.rglob("*") if p.is_file())
    changed = []
    for sp in src_files:
        dp = dest / sp.relative_to(src)
        if not dp.exists() or not filecmp.cmp(sp, dp, shallow=False):
            changed.append(str(dp))

    existed = dest.exists()
    if changed and not dry_run:
        for sp in src_files:
            dp = dest / sp.relative_to(src)
            dp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sp, dp)  # copy content only; never removes siblings

    if not changed:
        status = "up_to_date"
    elif dry_run:
        status = "would_update" if existed else "would_install"
    else:
        status = "updated" if existed else "installed"

    return {
        "status": status,
        "skill": SKILL_NAME,
        "source": str(src),
        "dest": str(dest),
        "changed": changed,
        "dry_run": dry_run,
    }
