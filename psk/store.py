"""On-disk `.ai/` canonical directory model: read/write/append, atomically.

Layout (inside the *target* repository):
    .ai/
      state.json     canonical current snapshot (pretty, human-diffable)
      events.jsonl   append-only history, one canonical-JSON event per line
      STATE.md       deterministic Markdown projection of state.json

Safety guarantees:
- Never overwrite an existing state.json silently (init must pass force=True).
- Atomic writes (temp file + os.replace) so a crash can't truncate state.
- Loading validates and rejects malformed/incompatible state.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .errors import StateExistsError, StateNotFoundError, ValidationError
from .models import Event, ProjectState, to_jsonable
from .projection import render_markdown
from .util import canonical_json, pretty_json
from .validation import validate_event, validate_state
import json

AI_DIR = ".ai"
STATE_FILE = "state.json"
EVENTS_FILE = "events.jsonl"
PROJECTION_FILE = "STATE.md"


def ai_dir(repo_root: str) -> Path:
    return Path(repo_root) / AI_DIR


def state_path(repo_root: str) -> Path:
    return ai_dir(repo_root) / STATE_FILE


def events_path(repo_root: str) -> Path:
    return ai_dir(repo_root) / EVENTS_FILE


def projection_path(repo_root: str) -> Path:
    return ai_dir(repo_root) / PROJECTION_FILE


def state_exists(repo_root: str) -> bool:
    return state_path(repo_root).exists()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".psk-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic on POSIX
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def save_state(repo_root: str, state: ProjectState, *, allow_create: bool = False,
               force: bool = False) -> None:
    """Persist state.json (+ projection). `allow_create` gates first write;
    `force` permits overwriting an existing file. Mutating updates set neither
    (the file already exists and we intend to update it)."""
    d = to_jsonable(state)
    validate_state(d)
    exists = state_exists(repo_root)
    if not exists and not allow_create:
        raise StateNotFoundError(f"no state at {state_path(repo_root)}")
    if exists and allow_create and not force:
        raise StateExistsError(
            f"{state_path(repo_root)} already exists; refusing to overwrite"
        )
    _atomic_write(state_path(repo_root), pretty_json(d))
    _atomic_write(projection_path(repo_root), render_markdown(state))


def load_state(repo_root: str) -> ProjectState:
    p = state_path(repo_root)
    if not p.exists():
        raise StateNotFoundError(f"no state at {p}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"state.json is not valid JSON: {exc}") from exc
    validate_state(d)
    return ProjectState.from_dict(d)


def append_event(repo_root: str, event: Event) -> None:
    d = to_jsonable(event)
    validate_event(d)
    events_path(repo_root).parent.mkdir(parents=True, exist_ok=True)
    with open(events_path(repo_root), "a", encoding="utf-8") as fh:
        fh.write(canonical_json(d) + "\n")


def read_events(repo_root: str) -> list:
    p = events_path(repo_root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
