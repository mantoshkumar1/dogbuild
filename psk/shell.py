"""DogBuild interactive shell — the persistent `dogBuild>` terminal experience.

`dogbuild start` opens this shell. The visible interface is DogBuild; Claude
Code runs underneath as the execution runtime, one turn at a time.

Honest boundaries, enforced here rather than implied:

- DogBuild is the control interface. Claude Code is the current execution
  runtime, invoked per turn via `claude --print` (no shell, argument list only).
- ChatGPT remains the master reviewer, but there is **no** automatic ChatGPT
  transport. When a reviewer decision is required the shell pauses and says so.
- Human authority remains supreme. Anything that needs a human blocks dispatch.

This is deliberately a plain line-oriented REPL: no curses, no daemon, no
terminal emulator, no background service. One turn at a time.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import brief as brief_mod, park as park_mod, store, util
from .governor import turngrant as turngrant_mod

# The visible prompt. Capitalization is part of the product; do not change it.
PROMPT = "dogBuild>"
PROMPT_STRING = PROMPT + " "

# Per-repository session pointer, so a later `dogbuild start` can resume the
# same underlying Claude conversation instead of starting cold.
SESSION_FILE = "dogbuild_session.json"

EXIT_WORDS = frozenset({"exit", "quit", "bye", ":q"})

DEFAULT_PERMISSION_MODE = "acceptEdits"


# ------------------------------------------------------------------ #
# Live state
# ------------------------------------------------------------------ #

def load_live(root: str) -> Tuple[dict, List[str]]:
    """Re-read live Git evidence + persistent DogBuild state."""
    return brief_mod.build(root)


def derive_stage(fields: dict) -> str:
    """Short, truthful operating-stage label for the banner.

    Derived from live state rather than stored, so it can never go stale:
    an active execution plan means delivery, otherwise maintenance.
    """
    product = fields.get("product") or "project"
    if fields.get("plan_current_task"):
        return f"{product} delivery"
    return f"{product} maintenance"


def _yesno(value: Any) -> str:
    return "Yes" if str(value).strip().lower() in ("yes", "true", "1") else "No"


_HISTORICAL_WARNING_PREFIXES = (
    "A past reviewer decision is for an older state",
    "The latest agent declaration references an older HEAD",
    "The last checkpoint was recorded at ",
)


def _visible_warnings(warnings: Optional[List[str]]) -> List[str]:
    """Hide routine history notices while preserving actionable failures."""
    return [
        warning
        for warning in (warnings or [])
        if not warning.startswith(_HISTORICAL_WARNING_PREFIXES)
    ]


def render_banner(fields: dict, warnings: Optional[List[str]] = None) -> str:
    """Render the branded DogBuild session banner shown above the first prompt."""
    human = _yesno(fields.get("human_decision_needed"))
    reason = fields.get("human_decision_reason") or ""
    milestone = fields.get("current_milestone", "(not set)")
    if fields.get("milestone_status") == "pending-next-milestone":
        milestone = "None — no task selected"

    lines = [
        "",
        "DogBuild",
        "",
        f"  Project:            {fields.get('product', '(unknown)')}",
        f"  Stage:              {derive_stage(fields)}",
        f"  Current milestone:  {milestone}",
        f"  Last verified:      {fields.get('current_verified_state', '(unknown)')}",
        f"  Human needed:       {human}" + (f" — {reason}" if human == "Yes" and reason else ""),
        "",
    ]
    visible_warnings = _visible_warnings(warnings)
    for warning in visible_warnings:
        lines.append(f"  Warning: {warning}")
    if visible_warnings:
        lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# State queries — answered locally, without calling Claude
# ------------------------------------------------------------------ #

# Work verbs that mean "this is a task", even if the sentence also asks a
# question. They stop a real instruction from being swallowed as a status read.
_WORK_WORDS = re.compile(
    r"\b(implement|build|fix|write|change|edit|add|remove|delete|refactor|"
    r"commit|push|deploy|install|upgrade|migrate|rename|create|generate|"
    r"run the|start the|make it|inspect|review the code)\b"
)

# "what" / "what's" / "whats" / "what is", followed by optional whitespace.
_W = r"what(?:'?s|s| is)?\s*"

_STATE_QUERY_PATTERNS: List[Tuple[str, str]] = [
    (_W + r"(?:currently )?(?:happening|going on|up)\b", "status"),
    (_W + r"(?:the )?(?:current )?(?:status|state|situation)\b", "status"),
    (r"where (are we|am i|do we stand|are things|is this)", "status"),
    (r"^(status|state|situation|where)$", "status"),
    (r"how (are things|is it going|are we doing)", "status"),
    (_W + r"(?:the )?next\b", "next"),
    (r"what should (i|we) (do|work on)( next)?", "next"),
    (r"^next$", "next"),
    (r"(did|do|have|are) (the )?tests? (pass|passed|passing|green|ok)", "tests"),
    (r"^tests?$", "tests"),
    (r"test results?", "tests"),
    (_W + r"(?:still )?(?:left|remaining|to do|outstanding)\b", "remaining"),
    (r"what remains", "remaining"),
    (r"how (much|far) (is )?(left|to go)", "remaining"),
    (r"(is|do|does) (a |any )?human (decision |input |approval )?(needed|required)", "human"),
    (r"human (decision|needed|input|approval)", "human"),
    (r"(do|does) (you|it|dogbuild) need me", "human"),
]

_COMPILED = [(re.compile(p), kind) for p, kind in _STATE_QUERY_PATTERNS]


def classify_state_query(text: str) -> Optional[str]:
    """Return the state-query kind for *text*, or None if it is real work.

    A state query is a short question about where the project stands. It must
    be answerable from DogBuild state alone, so Claude is never invoked for it.
    """
    probe = text.strip().lower().rstrip("?!. ")
    if not probe or len(probe) > 140:
        return None
    if _WORK_WORDS.search(probe):
        return None
    for pattern, kind in _COMPILED:
        if pattern.search(probe):
            return kind
    return None


def _tests_fragment(verified: str) -> str:
    """Pull the `tests: …` part out of the verified-state line."""
    marker = "tests:"
    lowered = verified.lower()
    if marker in lowered:
        return verified[lowered.index(marker) + len(marker):].strip()
    return "unknown"


def answer_state_query(fields: dict, warnings: List[str], kind: str) -> str:
    """Answer a state query in short plain English, from local state only."""
    product = fields.get("product", "This project")
    human = _yesno(fields.get("human_decision_needed"))
    reason = fields.get("human_decision_reason") or ""

    if kind == "status":
        # derive_stage() is product-qualified for the banner; don't say it twice.
        stage = derive_stage(fields)
        phrase = stage[len(product) + 1:] if stage.startswith(f"{product} ") else stage
        milestone = fields.get("current_milestone")
        if fields.get("milestone_status") == "pending-next-milestone":
            milestone = "None — no task selected"
        out = [
            f"{product} is in {phrase}.",
            f"Milestone: {milestone}",
            f"Current task: {fields.get('current_task', 'None')}",
            f"Live state: {fields.get('current_verified_state')}",
            f"Next step: {fields.get('next_step', fields.get('exact_next_action'))}",
        ]
        if fields.get("next_step") == "No task selected":
            out.append(f"When a task is selected: {fields.get('exact_next_action')}")
        if human == "Yes":
            out.append(f"A human decision is needed: {reason or 'see `review`'}.")
        else:
            out.append("No human decision is needed right now.")
        for warning in _visible_warnings(warnings):
            out.append(f"Warning: {warning}")
        return "\n".join(out)

    if kind == "next":
        out = [
            f"Current task: {fields.get('current_task', 'None')}",
            f"Next step: {fields.get('next_step', fields.get('exact_next_action'))}",
        ]
        if fields.get("next_step") == "No task selected":
            out.append(f"When a task is selected: {fields.get('exact_next_action')}")
        if human == "Yes":
            out.append(f"Blocked until a human decides: {reason or 'see `review`'}.")
        return "\n".join(out)

    if kind == "tests":
        fragment = _tests_fragment(fields.get("current_verified_state", ""))
        if fragment.startswith("not recorded"):
            return (
                "No test evidence is recorded for the current commit.\n"
                "Ask DogBuild to run the suite if you need fresh evidence."
            )
        return (
            f"Last recorded test evidence: {fragment}\n"
            "That is the last verified record, not a run just now. "
            "Ask DogBuild to run the suite if you need fresh evidence."
        )

    if kind == "remaining":
        remaining = fields.get("plan_remaining") or []
        blocked = fields.get("plan_blocked") or []
        if not fields.get("plan_current_task") and not remaining:
            return (
                "There is no active execution plan.\n"
                f"Next action: {fields.get('exact_next_action')}"
            )
        out = [f"Distance to delivery: {fields.get('plan_distance', 'unknown')}"]
        out.append(f"Remaining: {', '.join(remaining) if remaining else '(none)'}")
        if blocked:
            out.append(f"Blocked: {', '.join(blocked)}")
        return "\n".join(out)

    if kind == "human":
        if human == "Yes":
            return (
                f"Yes — a human decision is needed: {reason or 'a reviewer gate is blocking'}.\n"
                "DogBuild will not dispatch work to Claude until that is resolved."
            )
        return "No. Nothing is waiting on you right now."

    return f"Next action: {fields.get('exact_next_action')}"


# ------------------------------------------------------------------ #
# Session pointer (session recovery across `dogbuild start` runs)
# ------------------------------------------------------------------ #

def session_path(root: str) -> Path:
    return store.ai_dir(root) / SESSION_FILE


def load_session(root: str) -> Optional[dict]:
    """Load the recorded Claude session pointer, or None."""
    path = session_path(root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and isinstance(data.get("session_id"), str):
        return data
    return None


def save_session(root: str, session_id: str, turns: int) -> None:
    """Record the Claude session pointer. Best effort — never fatal."""
    try:
        store.atomic_write(
            session_path(root),
            json.dumps(
                {
                    "session_id": session_id,
                    "turns": turns,
                    "updated_at": util.now_iso(),
                    "runtime": "claude-code",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    except Exception:
        pass


# ------------------------------------------------------------------ #
# Claude Code runtime — one turn per user message
# ------------------------------------------------------------------ #

class ClaudeRunner:
    """Runs one Claude Code turn per call, keeping a single session alive.

    Uses `claude --print` with an argument list (never a shell string). The
    PreToolUse governor hook installed by the launcher still applies, so
    permission behavior is unchanged from an interactive Claude session.
    """

    def __init__(
        self,
        root: str,
        *,
        permission_mode: str = DEFAULT_PERMISSION_MODE,
        system_prompt: str = "",
        executable: Optional[str] = None,
        session_id: Optional[str] = None,
        resume: bool = False,
        runner: Optional[Callable[[List[str]], Tuple[int, str, str]]] = None,
    ) -> None:
        self.root = root
        self.permission_mode = permission_mode
        self.system_prompt = system_prompt
        self.executable = executable if executable is not None else shutil.which("claude")
        self.session_id = session_id or str(uuid.uuid4())
        self.resume = resume
        self.turns = 0
        self._runner = runner or self._subprocess_runner

    # -- argument construction ------------------------------------- #

    def build_args(self, message: str) -> List[str]:
        args = [
            self.executable or "claude",
            "--print",
            "--permission-mode",
            self.permission_mode,
        ]
        if self.resume or self.turns:
            args += ["--resume", self.session_id]
        else:
            args += ["--session-id", self.session_id]
            if self.system_prompt:
                args += ["--append-system-prompt", self.system_prompt]
        args.append(message)
        return args

    # -- execution --------------------------------------------------- #

    def _subprocess_runner(self, args: List[str]) -> Tuple[int, str, str]:
        proc = subprocess.run(
            args,
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout, proc.stderr

    def _is_stale_session(self, stderr: str) -> bool:
        low = (stderr or "").lower()
        return any(
            s in low
            for s in ("no conversation found", "session not found",
                      "no such session", "could not resume")
        )

    def send(self, message: str) -> Tuple[bool, str]:
        """Send one turn. Returns (ok, text). Never raises for runtime errors."""
        if not self.executable:
            return False, (
                "Claude Code is not installed or not on PATH, so DogBuild cannot "
                "run this turn.\nInstall it from "
                "https://docs.anthropic.com/en/docs/claude-code, then try again.\n"
                "DogBuild state commands still work."
            )

        code, out, err = self._runner(self.build_args(message))

        # A recovered session may no longer exist. Start a fresh one once.
        if code != 0 and (self.resume or self.turns) and self._is_stale_session(err):
            self.session_id = str(uuid.uuid4())
            self.resume = False
            self.turns = 0
            code, out, err = self._runner(self.build_args(message))

        if code != 0:
            detail = (err or out or "").strip()
            return False, "Claude Code did not complete this turn." + (
                f"\n{detail}" if detail else ""
            )

        self.turns += 1
        return True, (out or "").strip()


# ------------------------------------------------------------------ #
# The shell
# ------------------------------------------------------------------ #

HELP_TEXT = """DogBuild commands (answered from local state, no Claude call):

  help              show this list
  status            live project status in plain English
  next              the exact next action
  plan              execution plan and distance to delivery
  parked            parked ideas
  review            reviewer gate and how a ChatGPT decision is obtained
  refresh           re-read live Git evidence and DogBuild state
  mode              runtime, permission mode, session
  clear             clear the screen
  exit / quit       leave DogBuild (Ctrl-D also works)

Anything else is sent to Claude Code, which runs underneath as the execution
runtime. Questions such as "What's happening?" are answered from DogBuild
state without invoking Claude."""


class DogBuildShell:
    """The persistent `dogBuild>` REPL."""

    def __init__(
        self,
        root: str,
        *,
        permission_mode: str = DEFAULT_PERMISSION_MODE,
        system_prompt: str = "",
        claude: Optional[ClaudeRunner] = None,
        input_fn: Optional[Callable[[str], str]] = None,
        output_fn: Optional[Callable[[str], None]] = None,
        resume: bool = True,
    ) -> None:
        self.root = root
        self.permission_mode = permission_mode
        self._input = input_fn or input
        self._write = output_fn or (lambda s: print(s))
        self.fields: dict = {}
        self.warnings: List[str] = []
        self.recovered = False

        recovered_id = None
        if resume and claude is None:
            prior = load_session(root)
            if prior:
                recovered_id = prior["session_id"]
                self.recovered = True

        self.claude = claude or ClaudeRunner(
            root,
            permission_mode=permission_mode,
            system_prompt=system_prompt,
            session_id=recovered_id,
            resume=bool(recovered_id),
        )

    # -- helpers ------------------------------------------------------ #

    def refresh(self) -> None:
        """Re-read live state. Failures degrade to a warning, never a crash."""
        try:
            self.fields, self.warnings = load_live(self.root)
        except Exception as exc:  # state unreadable mid-session
            self.warnings = [f"could not read DogBuild state: {exc}"]

    def say(self, text: str = "") -> None:
        self._write(text)

    def _respond(self, text: str) -> None:
        """Emit a response and leave a blank line before the next prompt."""
        if text:
            self.say(text)
        self.say("")

    def _claude_message(self, owner_message: str) -> str:
        """Attach fresh repository truth to every Claude turn.

        Recovered Claude sessions are useful for conversational continuity, but
        their remembered branch, HEAD, tests, or task can be stale. This live
        block is deliberately repeated on every turn and overrides that memory.
        """
        return (
            "[DogBuild live context — authoritative for this turn]\n"
            f"Repository: {self.root}\n"
            f"Live state: {self.fields.get('current_verified_state', '(unknown)')}\n"
            f"Current task: {self.fields.get('current_task', 'None')}\n"
            f"Next step: {self.fields.get('next_step', self.fields.get('exact_next_action', ''))}\n"
            "If earlier conversation memory conflicts with this block or with "
            "fresh repository inspection, ignore the older claim. Do not present "
            "older commit, test, or task details as current. If a tool call is "
            "denied, do not retry the identical action unless the owner or the "
            "machine-enforced authorization has changed.\n"
            "[Owner request]\n"
            f"{owner_message}"
        )

    # -- built-in commands -------------------------------------------- #

    def _builtin_help(self) -> str:
        return HELP_TEXT

    def _builtin_status(self) -> str:
        self.refresh()
        return answer_state_query(self.fields, self.warnings, "status")

    def _builtin_next(self) -> str:
        self.refresh()
        return answer_state_query(self.fields, self.warnings, "next")

    def _builtin_plan(self) -> str:
        self.refresh()
        return answer_state_query(self.fields, self.warnings, "remaining")

    def _builtin_parked(self) -> str:
        try:
            ideas = park_mod.lst(self.root)
        except Exception as exc:
            return f"Could not read parked ideas: {exc}"
        if not ideas:
            return "No parked ideas."
        lines = [f"{len(ideas)} parked idea(s):"]
        for idea in ideas:
            lines.append(f"  · {idea.get('title', '(untitled)')} — {idea.get('reason', '')}")
        return "\n".join(lines)

    def _builtin_review(self) -> str:
        self.refresh()
        return (
            f"Reviewer policy:     {self.fields.get('reviewer_policy', '(none)')}\n"
            f"Current gate:        {self.fields.get('current_gate', 'none')}\n"
            f"Pending conditions:  {self.fields.get('pending_conditions', 0)}\n"
            f"Human decision:      {_yesno(self.fields.get('human_decision_needed'))}\n"
            "\n"
            "ChatGPT is the master reviewer. DogBuild does not talk to ChatGPT\n"
            "automatically — transport is manual in this alpha. To get a decision:\n"
            "  1. dogbuild review request .      (writes the packet)\n"
            "  2. paste it into ChatGPT yourself\n"
            "  3. dogbuild review import . <file>"
        )

    def _builtin_refresh(self) -> str:
        self.refresh()
        return render_banner(self.fields, self.warnings).strip("\n")

    def _builtin_mode(self) -> str:
        return (
            "Interface:        DogBuild (this prompt)\n"
            "Execution runtime: Claude Code"
            + (f" ({self.claude.executable})" if self.claude.executable else " (not installed)")
            + "\n"
            "Master reviewer:  ChatGPT (manual transport)\n"
            f"Permission mode:  {self.permission_mode}\n"
            f"Repository:       {self.root}\n"
            f"Claude session:   {self.claude.session_id}"
            + (" (recovered)" if self.recovered else " (new)")
            + f", {self.claude.turns} turn(s) this run"
        )

    def _builtin_clear(self) -> str:
        if sys.stdout.isatty():
            self._write("\033[2J\033[H")
        return ""

    BUILTINS: Dict[str, str] = {
        "help": "_builtin_help",
        "?": "_builtin_help",
        "status": "_builtin_status",
        "state": "_builtin_status",
        "next": "_builtin_next",
        "plan": "_builtin_plan",
        "parked": "_builtin_parked",
        "review": "_builtin_review",
        "reviewer": "_builtin_review",
        "refresh": "_builtin_refresh",
        "mode": "_builtin_mode",
        "clear": "_builtin_clear",
    }

    # -- dispatch ------------------------------------------------------ #

    def _pause_for_human(self) -> Optional[str]:
        """Return a pause message if a human/ChatGPT decision blocks work."""
        if _yesno(self.fields.get("human_decision_needed")) != "Yes":
            return None
        reason = self.fields.get("human_decision_reason") or "a reviewer gate is blocking"
        return (
            f"DogBuild is paused: {reason}.\n"
            "This needs a decision from you or from ChatGPT (the master reviewer).\n"
            "DogBuild cannot reach ChatGPT automatically in this alpha — type "
            "`review` for the manual steps.\n"
            "No work was sent to Claude."
        )

    def handle(self, line: str) -> bool:
        """Handle one input line. Returns False when the shell should exit."""
        text = line.strip()
        if not text:
            return True

        lowered = text.lower()
        word = lowered.rstrip("?!. ") or lowered
        if word in EXIT_WORDS:
            return False

        method = self.BUILTINS.get(lowered) or self.BUILTINS.get(word)
        if method:
            self._respond(getattr(self, method)())
            return True

        kind = classify_state_query(text)
        if kind:
            self.refresh()
            self._respond(answer_state_query(self.fields, self.warnings, kind))
            return True

        # Real work — Claude Code runs underneath.
        self.refresh()
        paused = self._pause_for_human()
        if paused:
            self._respond(paused)
            return True

        # A direct owner instruction that only asks to look and verify may
        # authorize this one turn, even when autonomy is stopped. The grant is
        # created here and destroyed in the finally below — never reused.
        grant = self._open_turn_grant(text)

        self.say("  … Claude Code is working (DogBuild is the interface).")
        try:
            ok, response = self.claude.send(self._claude_message(text))
        except KeyboardInterrupt:
            self._respond("  (interrupted — nothing further was sent)")
            return True
        finally:
            self._close_turn_grant(grant)

        if ok:
            save_session(self.root, self.claude.session_id, self.claude.turns)
        self._respond(response or "(no output)")
        return True

    # -- turn-scoped owner authorization -------------------------------- #

    def _open_turn_grant(self, text: str) -> Optional[dict]:
        """Create a turn grant for *text* if it is a clear look-and-verify ask."""
        try:
            grant = turngrant_mod.create(self.root, text)
        except Exception:
            return None
        if grant:
            if grant.get("commit_allowed"):
                paths = ", ".join(grant.get("allowed_commit_paths") or [])
                self.say(
                    "  Owner authorization for this turn: inspect and commit "
                    f"only the existing change to {paths}. No edits, installs, "
                    "push, deploy, publish, or network."
                )
            else:
                self.say(
                    "  Owner authorization for this turn: read the repository "
                    "and run existing tests. No edits, commits, installs, or network."
                )
        return grant

    def _close_turn_grant(self, grant: Optional[dict]) -> None:
        """Expire the grant. Runs after every turn — success, failure, or Ctrl-C."""
        if not grant:
            return
        try:
            turngrant_mod.expire(self.root, reason="turn complete")
        except Exception:
            pass

    # -- main loop ------------------------------------------------------ #

    def run(self) -> int:
        try:  # line editing + history when available; never required
            import readline  # noqa: F401
        except Exception:
            pass

        # A grant must never survive the process that created it. Anything
        # left behind by a crash or a kill is dead on arrival.
        self._close_turn_grant({"turn_id": "startup-sweep"})

        self.refresh()
        self.say(render_banner(self.fields, self.warnings))
        if self.recovered:
            self.say("  Recovered the previous DogBuild session for this repository.")
            self.say("")
        self.say('  Type `help` for commands, or just ask "What\'s happening?".')
        self.say("")

        while True:
            try:
                line = self._input(PROMPT_STRING)
            except EOFError:
                self.say("")
                break
            except KeyboardInterrupt:
                self.say("")
                self.say("  (type `exit` to leave DogBuild)")
                continue

            try:
                if not self.handle(line):
                    break
            except Exception as exc:  # a bad turn must not kill the session
                self._respond(f"  DogBuild hit an error on that turn: {exc}")

        self._close_turn_grant({"turn_id": "shutdown-sweep"})
        self.say("Leaving DogBuild. Project state stays in .ai/ — nothing is lost.")
        return 0


def run_shell(
    root: str,
    *,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    system_prompt: str = "",
    resume: bool = True,
) -> int:
    """Entry point used by the launcher."""
    return DogBuildShell(
        root,
        permission_mode=permission_mode,
        system_prompt=system_prompt,
        resume=resume,
    ).run()
