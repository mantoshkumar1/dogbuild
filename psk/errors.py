"""Typed error hierarchy for Project State Keeper."""

from __future__ import annotations


class PSKError(Exception):
    """Base class for all Project State Keeper errors."""


class GitError(PSKError):
    """A git subprocess failed."""


class NotAGitRepoError(GitError):
    """The target path is not inside a git work tree."""


class StateExistsError(PSKError):
    """Refusing to overwrite existing `.ai/state.json` (use force explicitly)."""


class StateNotFoundError(PSKError):
    """No `.ai/state.json` found where one was expected."""


class ValidationError(PSKError):
    """State or event is structurally malformed."""


class IncompatibleStateError(ValidationError):
    """State exists but its schema version is not compatible with this build."""
