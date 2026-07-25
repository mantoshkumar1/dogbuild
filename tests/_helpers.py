"""Test helpers: build throwaway git repositories in temp dirs."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args], check=True, capture_output=True, text=True
    )
    return proc.stdout


def make_repo(with_commit: bool = True) -> str:
    d = tempfile.mkdtemp(prefix="psk-test-")
    git(d, "init", "-b", "main")
    git(d, "config", "user.email", "t@example.com")
    git(d, "config", "user.name", "Test")
    if with_commit:
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
            fh.write("# test\n")
        git(d, "add", "-A")
        git(d, "commit", "-m", "init")
    return d


def cleanup(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
