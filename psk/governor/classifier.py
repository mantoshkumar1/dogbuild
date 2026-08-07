"""Risk classifier — deterministic 5-tier action classification.

Every action is classified into one of five tiers based on its observable
properties.  The classifier is explainable: every decision includes
machine-readable reasons.

Tier 0 — Read-only and routine (git status, file reads, approved URL fetch)
Tier 1 — Reversible local execution (tests, builds, task-scoped writes/commits)
Tier 2 — Material but recoverable (dependency install, branch change, broad edits)
Tier 3 — High risk (destructive git, rm -rf, credential access, sudo)
Tier 4 — External or production impact (push, merge, deploy, publish)
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass, field
from typing import List, Optional

from .parser import split_all_segments
from .policy import ActionLevel, ExecutionPolicy


class RiskTier(str, enum.Enum):
    TIER_0_READ_ONLY = "tier_0_read_only"
    TIER_1_REVERSIBLE = "tier_1_reversible"
    TIER_2_MATERIAL = "tier_2_material"
    TIER_3_HIGH_RISK = "tier_3_high_risk"
    TIER_4_EXTERNAL = "tier_4_external"


@dataclass
class ActionClassification:
    """Result of classifying a single atomic action."""
    tier: RiskTier
    action_class: str
    reasons: List[str] = field(default_factory=list)
    confidence: float = 1.0  # 0.0–1.0; low confidence → conservative escalation


# --- Patterns for command classification ---

# Tier 4: external/production
_TIER4_CMDS = {"git push", "git merge", "npm publish", "pip upload",
               "docker push", "kubectl apply", "terraform apply",
               "aws deploy", "gcloud deploy", "heroku", "netlify deploy",
               "vercel deploy"}
_TIER4_PATTERNS = [
    re.compile(r"\bgit\s+push\b"),
    re.compile(r"\bgit\s+merge\b"),
    re.compile(r"\bnpm\s+publish\b"),
    re.compile(r"\bdeploy\b"),
    re.compile(r"\bkubectl\s+apply\b"),
]

# Tier 3: high risk
_TIER3_PATTERNS = [
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-[a-z]*f"),
    re.compile(r"\bgit\s+branch\s+-[dD]\b"),
    re.compile(r"\brm\s+-[a-z]*r[a-z]*f\b"),
    re.compile(r"\brm\s+-[a-z]*f[a-z]*r\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bchmod\s+777\b"),
    re.compile(r"\bchown\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bcurl\b.*\|\s*(?:ba)?sh\b"),  # pipe into shell
    re.compile(r"\bwget\b.*\|\s*(?:ba)?sh\b"),
]

# Secret/credential patterns
_SECRET_PATTERNS = [
    re.compile(r"\b(AWS_SECRET|AWS_ACCESS_KEY|GITHUB_TOKEN|API_KEY|"
               r"DATABASE_URL|DB_PASSWORD|PRIVATE_KEY)\b", re.I),
    re.compile(r"~/\.ssh\b"),
    re.compile(r"~/\.aws\b"),
    re.compile(r"\.env\b"),
    re.compile(r"\bcat\s+.*\.(pem|key|crt)\b"),
]

# Tier 2: material but recoverable
_TIER2_PATTERNS = [
    re.compile(r"\bnpm\s+install\b"),
    re.compile(r"\bpip\s+install\b"),
    re.compile(r"\byarn\s+add\b"),
    re.compile(r"\bapt\s+install\b"),
    re.compile(r"\bbrew\s+install\b"),
    re.compile(r"\bgit\s+checkout\b(?!.*--\s)"),  # branch change (not file restore)
    re.compile(r"\bgit\s+switch\b"),
]

# Tier 1: reversible local
_TIER1_PATTERNS = [
    re.compile(r"\bnpm\s+(test|run)\b"),
    # Anchored to the start of a segment, which normalize_interpreter has
    # already canonicalized. Unanchored, a token such as
    # `--interpreter=/usr/bin/python3 -m pytest` read as an ordinary test run;
    # the spelling alternatives remain as a backstop if normalization misses.
    re.compile(r"^(?:python[0-9.]*|py)\s+-m\s+(unittest|pytest)\b"),
    re.compile(r"\bjest\b"),
    re.compile(r"\bmocha\b"),
    re.compile(r"\bmake\b"),
    re.compile(r"\bnpm\s+run\s+build\b"),
    re.compile(r"\bgit\s+commit\b"),
    re.compile(r"\bgit\s+add\b"),
    # A non-option argument creates a branch. Read-only option forms such as
    # `git branch -vv` are handled explicitly in Tier 0 below.
    re.compile(r"\bgit\s+branch\s+(?!-)\S+"),
]

# Tier 0: read-only.
#
# These are anchored to the start of a command segment. An unanchored word
# match let any command inherit Tier 0 from an unrelated fragment: both a
# trailing `| tail` and an argument such as `--out find.txt` were enough to
# turn an unrecognized command into "read-only".
_TIER0_PATTERNS = [
    re.compile(r"^git\s+(status|diff|log|show|branch\s*$)\b"),
    re.compile(
        r"^git\s+branch"
        r"(?:\s+(?:-a|-r|-v|-vv|--all|--remotes|--verbose|--list|"
        r"--show-current|--no-color|--color(?:=(?:always|never|auto))?))*\s*$"
    ),
    # Inspection-only plumbing. None of these match an earlier tier, so they
    # would otherwise fall through to the conservative unknown-command default.
    re.compile(r"^git\s+(rev-parse|describe|blame|shortlog|ls-files|"
               r"ls-tree|cat-file|symbolic-ref|config\s+--get)\b"),
    # `git remote` only in its read-only forms — never add/remove/set-url.
    re.compile(r"^git\s+remote\s*(-v|--verbose|show\b|get-url\b)?\s*$"),
    re.compile(r"^(cat|head|tail|less|more|wc|grep|rg|find|fd|ls|tree|pwd|echo)\b"),
]

# --- Interpreter normalization -------------------------------------- #
#
# Classification must not depend on how an interpreter happens to be spelled.
# `python3 -m pytest` reading differently from `python -m pytest` is what let a
# test run escape Tier 1 in the first place.

# Leading `VAR=value ` assignments.
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*\s+")
# A directory prefix. Deliberately path-shaped rather than `\S*/`: any
# non-space run would let a token such as `--interpreter=/usr/bin/python3`
# induce normalization and be read as an ordinary test run.
_PATH_PREFIX = r"(?:[\w.\-~/]*/)?"
# An `env` / `/usr/bin/env` launcher prefix.
_ENV_LAUNCHER = re.compile(rf"^{_PATH_PREFIX}env\s+")
# `env` options that do not change how the remaining words are parsed, so the
# interpreter after them is still the interpreter. `-S`/`--split-string` is
# deliberately absent: it re-splits the rest of the line, so a command using it
# is left unnormalized and falls through to the conservative default.
_ENV_OPTION_WITH_VALUE = re.compile(r"^(?:-u|-C)\s+\S+\s+")
_ENV_OPTION_INLINE = re.compile(
    r"^(?:--unset=\S+|--chdir=\S+|--ignore-environment|-i|-)\s+"
)
# A Python interpreter token: optional path, optional version, optional .exe.
_INTERPRETER = re.compile(
    rf"^{_PATH_PREFIX}(?:python[0-9.]*|py)(?:\.exe)?(?=\s|$)"
)


def _strip_env_assignments(text: str) -> str:
    while True:
        stripped = _ENV_ASSIGNMENT.sub("", text)
        if stripped == text:
            return text
        text = stripped


def normalize_interpreter(cmd: str) -> str:
    """Rewrite a Python interpreter invocation to a canonical `python …`.

    Handles `python`, `python3`, versioned forms like `python3.13`, absolute
    and relative interpreter paths, `python.exe`, `py`, leading `VAR=value`
    assignments, and `env` / `/usr/bin/env` launcher forms including the
    options that leave the following words intact (`-i`, `-u NAME`, `-C DIR`
    and their long spellings). `env -S` is not normalized, because it re-splits
    the rest of the line.

    This affects classification only. The command that actually executes, and
    the command recorded in the audit trail, are never rewritten.
    """
    text = _strip_env_assignments(cmd.strip())

    launcher = _ENV_LAUNCHER.match(text)
    if launcher:
        text = text[launcher.end():]
        # `env` accepts options and assignments in any order before the command.
        while True:
            before = text
            text = _strip_env_assignments(text)
            option = (_ENV_OPTION_WITH_VALUE.match(text)
                      or _ENV_OPTION_INLINE.match(text))
            if option:
                text = text[option.end():]
            if text == before:
                break

    match = _INTERPRETER.match(text)
    if not match:
        return cmd.strip()
    return "python" + text[match.end():]


# Ordering used to pick the riskiest stage of a compound command.
_TIER_RANK = {
    RiskTier.TIER_0_READ_ONLY: 0,
    RiskTier.TIER_1_REVERSIBLE: 1,
    RiskTier.TIER_2_MATERIAL: 2,
    RiskTier.TIER_3_HIGH_RISK: 3,
    RiskTier.TIER_4_EXTERNAL: 4,
}

# Network tools
_NETWORK_CMDS = re.compile(r"\b(curl|wget|http|fetch)\b")
_HTTP_MUTATING = re.compile(r"-X\s*(POST|PUT|DELETE|PATCH)\b", re.I)
_HTTP_DATA = re.compile(r"(-d\s|--data\s|-F\s|--form\s|--upload)")
_HTTP_AUTH = re.compile(
    r'(-H\s+["\']?Authorization\b|--header\s+["\']?Authorization\b|'
    r'-u\s|--user\s|-H\s+["\']?Cookie\b|'
    r'Bearer\s+\S|Token\s+\S)',
    re.I,
)

# Known paid / sensitive API endpoints that must never be treated as
# generic public web research.
_PAID_API_DOMAINS = frozenset({
    "api.openai.com",
    "api.anthropic.com",
    "api.stripe.com",
    "api.twilio.com",
    "api.sendgrid.com",
    "api.github.com",
})


def classify_command(cmd: str, policy: Optional[ExecutionPolicy] = None) -> ActionClassification:
    """Classify a shell command, compound commands included.

    A compound command is classified by its riskiest stage. The whole string is
    always classified too, so cross-stage patterns such as `curl ... | sh` keep
    their Tier 3 reading; the result is the highest tier of the two views, which
    means this can only ever escalate, never soften, an earlier decision.
    """
    stripped = cmd.strip()
    worst = _classify_segment(stripped, policy)

    segments = split_all_segments(stripped)
    if len(segments) <= 1:
        return worst

    for segment in segments:
        cls = _classify_segment(segment, policy)
        if _TIER_RANK[cls.tier] > _TIER_RANK[worst.tier]:
            worst = cls
            worst.reasons.append(
                f"compound command classified by its riskiest stage: {segment}"
            )

    return worst


def _classify_segment(cmd: str, policy: Optional[ExecutionPolicy] = None) -> ActionClassification:
    """Classify one atomic command segment.

    Returns an ActionClassification with tier, action_class, and reasons.
    """
    cmd_stripped = normalize_interpreter(cmd)
    reasons: List[str] = []
    if cmd_stripped != cmd.strip():
        reasons.append(f"interpreter normalized for classification: {cmd_stripped}")

    # Check Tier 4 first (highest risk)
    for pat in _TIER4_PATTERNS:
        if pat.search(cmd_stripped):
            reasons.append(f"matches external/production pattern: {pat.pattern}")
            action_class = _action_class_for_tier4(cmd_stripped)
            return ActionClassification(
                tier=RiskTier.TIER_4_EXTERNAL,
                action_class=action_class,
                reasons=reasons,
            )

    # Check secrets/credentials
    for pat in _SECRET_PATTERNS:
        if pat.search(cmd_stripped):
            reasons.append(f"accesses secrets or credentials: {pat.pattern}")
            return ActionClassification(
                tier=RiskTier.TIER_3_HIGH_RISK,
                action_class="secrets_access",
                reasons=reasons,
            )

    # Check Tier 3
    for pat in _TIER3_PATTERNS:
        if pat.search(cmd_stripped):
            reasons.append(f"matches high-risk pattern: {pat.pattern}")
            action_class = "destructive_commands"
            if "sudo" in cmd_stripped:
                action_class = "destructive_commands"
            return ActionClassification(
                tier=RiskTier.TIER_3_HIGH_RISK,
                action_class=action_class,
                reasons=reasons,
            )

    # Check network commands
    if _NETWORK_CMDS.search(cmd_stripped):
        return _classify_network_cmd(cmd_stripped, policy)

    # Check Tier 2
    for pat in _TIER2_PATTERNS:
        if pat.search(cmd_stripped):
            reasons.append(f"material but recoverable: {pat.pattern}")
            action_class = _action_class_for_tier2(cmd_stripped)
            return ActionClassification(
                tier=RiskTier.TIER_2_MATERIAL,
                action_class=action_class,
                reasons=reasons,
            )

    # Check Tier 1
    for pat in _TIER1_PATTERNS:
        if pat.search(cmd_stripped):
            reasons.append(f"reversible local action: {pat.pattern}")
            action_class = _action_class_for_tier1(cmd_stripped)
            return ActionClassification(
                tier=RiskTier.TIER_1_REVERSIBLE,
                action_class=action_class,
                reasons=reasons,
            )

    # Check Tier 0
    for pat in _TIER0_PATTERNS:
        if pat.search(cmd_stripped):
            reasons.append(f"read-only operation: {pat.pattern}")
            return ActionClassification(
                tier=RiskTier.TIER_0_READ_ONLY,
                action_class="repository_read",
                reasons=reasons,
            )

    # Default: unknown → conservative (Tier 2 with low confidence)
    reasons.append("command not recognized; classified conservatively")
    return ActionClassification(
        tier=RiskTier.TIER_2_MATERIAL,
        action_class="repository_write",
        reasons=reasons,
        confidence=0.5,
    )


def _classify_network_cmd(cmd: str, policy: Optional[ExecutionPolicy]) -> ActionClassification:
    """Classify a network command (curl, wget, etc.)."""
    reasons: List[str] = []

    # Check for pipe into shell (already caught above, but defensive)
    if re.search(r"\|\s*(?:ba)?sh\b", cmd):
        reasons.append("pipes downloaded content into a shell")
        return ActionClassification(
            tier=RiskTier.TIER_3_HIGH_RISK,
            action_class="destructive_commands",
            reasons=reasons,
        )

    # Check for authentication headers / credentials in the request.
    # These are never generic public web research.
    if _HTTP_AUTH.search(cmd):
        reasons.append("request carries authentication credentials")
        return ActionClassification(
            tier=RiskTier.TIER_3_HIGH_RISK,
            action_class="secrets_access",
            reasons=reasons,
        )

    # Check for mutating HTTP methods (POST/PUT/DELETE/PATCH or data upload)
    if _HTTP_MUTATING.search(cmd) or _HTTP_DATA.search(cmd):
        reasons.append("uses mutating HTTP method or sends data")
        return ActionClassification(
            tier=RiskTier.TIER_3_HIGH_RISK,
            action_class="network_unapproved",
            reasons=reasons,
        )

    # Extract URL domain
    url_match = re.search(r'https?://([^/\s"\']+)', cmd)
    if url_match:
        domain = url_match.group(1).split(":")[0]  # strip port
        reasons.append(f"HTTPS GET to {domain}")

        # Paid / sensitive API endpoints are never public web research
        if domain in _PAID_API_DOMAINS:
            reasons.append(f"{domain} is a paid/sensitive API endpoint")
            return ActionClassification(
                tier=RiskTier.TIER_4_EXTERNAL,
                action_class="production_access",
                reasons=reasons,
            )

        if policy and policy.domain_allowed(domain):
            reasons.append(f"{domain} is in the approved domain list")
            # Check output path
            output_match = re.search(r'-o\s+["\']?([^\s"\']+)', cmd)
            if output_match:
                output_path = output_match.group(1)
                if policy.path_in_write_root(output_path):
                    reasons.append(f"output path {output_path} is in an approved write root")
                    reasons.append("no repository mutation")
                    reasons.append("no credentials involved")
                    return ActionClassification(
                        tier=RiskTier.TIER_0_READ_ONLY,
                        action_class="public_web_research",
                        reasons=reasons,
                    )
                elif policy.path_is_protected(output_path):
                    reasons.append(f"output path {output_path} is protected")
                    return ActionClassification(
                        tier=RiskTier.TIER_3_HIGH_RISK,
                        action_class="secrets_access",
                        reasons=reasons,
                    )
            # Domain approved but no output or unknown output path
            reasons.append("approved domain, read-only fetch")
            return ActionClassification(
                tier=RiskTier.TIER_0_READ_ONLY,
                action_class="public_web_research",
                reasons=reasons,
            )
        else:
            # Unapproved domain → require approval, not auto-execute
            reasons.append("domain not in approved list")
            return ActionClassification(
                tier=RiskTier.TIER_2_MATERIAL,
                action_class="network_unapproved",
                reasons=reasons,
                confidence=0.7,
            )

    # Network command without recognizable URL
    reasons.append("network command without recognizable HTTPS URL")
    return ActionClassification(
        tier=RiskTier.TIER_2_MATERIAL,
        action_class="network_unapproved",
        reasons=reasons,
        confidence=0.5,
    )


def _action_class_for_tier4(cmd: str) -> str:
    if "push" in cmd:
        return "git_push"
    if "merge" in cmd:
        return "merge"
    if "publish" in cmd or "deploy" in cmd:
        return "deploy"
    return "production_access"


def _action_class_for_tier2(cmd: str) -> str:
    if any(x in cmd for x in ("npm install", "pip install", "yarn add",
                               "apt install", "brew install")):
        return "dependency_install"
    if "checkout" in cmd or "switch" in cmd:
        return "branch_change"
    return "repository_write"


# Tier 1 actions, recognized by the verb that starts the segment. The segment
# has already been normalized, so every Python interpreter spelling arrives as
# a leading `python`.
_TIER1_ACTION_VERBS = (
    (re.compile(rf"^{_PATH_PREFIX}git\s+commit\b"), "git_commit"),
    (re.compile(rf"^{_PATH_PREFIX}git\s+add\b"), "repository_write"),
    (re.compile(rf"^{_PATH_PREFIX}git\s+branch\b"), "branch_create"),
    (re.compile(r"^(?:python[0-9.]*|py)\s+-m\s+(?:unittest|pytest)\b"),
     "tests_and_builds"),
    # `npm test` is the test script by definition. `npm run <script>` is
    # arbitrary script execution, so only recognized test and build scripts
    # count: otherwise `npm run publish` or `npm run migrate` would be a test
    # run, and a read-and-verify grant would permit it. Anything else falls
    # through to the repository_write default, which no grant permits.
    (re.compile(rf"^{_PATH_PREFIX}npm\s+test\b"), "tests_and_builds"),
    # Exactly the owner-approved scripts. Names like `check` or `coverage` are
    # bound to whatever package.json says, so recognizing them by category
    # would reopen the same widening in a narrower form.
    # The script name must END here, not merely hit a word boundary: `\b` sits
    # between `build` and `:`, so `npm run build:prod` matched and a
    # read-and-verify grant permitted it. Same for build-and-deploy,
    # test-and-publish, build.release. `build` gets no exception below:
    # `build:prod` is the documented case that motivated this whole rule, and
    # a namespaced build script is more likely to reach a deploy-shaped step
    # than a namespaced test script is.
    (re.compile(rf"^{_PATH_PREFIX}npm\s+run\s+build(?:\s|$)"),
     "tests_and_builds"),
    # `test:<name>` is a ubiquitous npm convention for organizing test scripts
    # (test:unit, test:e2e, test:watch, ...) and, owner-approved, is trusted
    # the same as bare `test`. Only a colon-namespaced suffix qualifies —
    # `test-and-deploy` and `test.something` still fall through below.
    (re.compile(rf"^{_PATH_PREFIX}npm\s+run\s+test(?::[\w-]+)?(?:\s|$)"),
     "tests_and_builds"),
    # `npx jest` and `./node_modules/.bin/jest` are genuine invocations and
    # already reach Tier 1 through the unanchored tier patterns, so the verb
    # table has to recognize them too or they fall back to repository_write.
    (re.compile(rf"^(?:npx\s+)?{_PATH_PREFIX}(?:jest|mocha|make)\b"),
     "tests_and_builds"),
)


def _action_class_for_tier1(cmd: str) -> str:
    """Derive the action class from the segment's own verb.

    Substring matching over the whole line put `git commit tests/test_x.py`
    into tests_and_builds, because "test" appeared in a path and was checked
    before "git commit". That is not cosmetic: a turn grant permits
    tests_and_builds, and an action class other than git_commit skips the
    exact-commit validation entirely, so the commit ran with no diff, message,
    or path check. A repository whose own checkout path contains "build" made
    it worse, matching the build heuristic on any absolute path.

    Arguments never decide the action class now — only the verb does. Leading
    `VAR=value` assignments are stripped first, since they precede the verb
    rather than being one: `FOO=bar npm test` is still a test run.
    """
    stripped = _strip_env_assignments(cmd.strip())
    for pattern, action_class in _TIER1_ACTION_VERBS:
        if pattern.match(stripped):
            return action_class
    return "repository_write"
