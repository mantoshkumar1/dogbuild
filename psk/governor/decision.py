"""Decision engine — deterministic execution decisions from policy + classification.

The same input and policy always produce the same decision.  No hidden
heuristic state.  Every decision is auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .classifier import ActionClassification, RiskTier, classify_command
from .parser import AtomicAction, NormalizedPlan, normalize_for_policy, parse_compound
from .policy import ActionLevel, ExecutionPolicy


@dataclass
class ApprovalRequest:
    """A structured approval request for the user."""
    task_id: str
    summary: str
    action_count: int
    domains: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    write_locations: List[str] = field(default_factory=list)
    expected_effects: List[str] = field(default_factory=list)
    excluded: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "summary": self.summary,
            "action_count": self.action_count,
            "domains": self.domains,
            "methods": self.methods,
            "write_locations": self.write_locations,
            "expected_effects": self.expected_effects,
            "excluded": self.excluded,
        }


@dataclass
class ExecutionDecision:
    """The output of the decision engine for a proposed action or plan."""
    decision: str  # "auto_execute", "allow_agent", "request_approval", "deny"
    classification: str
    reasons: List[str] = field(default_factory=list)
    normalized_plan: Optional[NormalizedPlan] = None
    policy_context: str = ""
    approval_request: Optional[ApprovalRequest] = None
    safe_alternative: Optional[NormalizedPlan] = None

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "decision": self.decision,
            "classification": self.classification,
            "reasons": self.reasons,
        }
        if self.normalized_plan:
            d["normalized_plan"] = {
                "original": self.normalized_plan.original,
                "actions": [{"command": a.command, "description": a.description}
                            for a in self.normalized_plan.actions],
                "confidence": self.normalized_plan.confidence,
                "warnings": self.normalized_plan.warnings,
            }
        if self.policy_context:
            d["policy_context"] = self.policy_context
        if self.approval_request:
            d["approval_request"] = self.approval_request.to_dict()
        if self.safe_alternative:
            d["safe_alternative"] = {
                "actions": [{"command": a.command, "description": a.description}
                            for a in self.safe_alternative.actions],
            }
        return d


def decide(
    command: str,
    policy: ExecutionPolicy,
    *,
    agent: str = "claude",
    scratch_dir: Optional[str] = None,
) -> ExecutionDecision:
    """Make an execution decision for a proposed command.

    Parses the command, classifies each atomic action, checks against policy,
    and returns a deterministic decision.
    """
    if not policy.active:
        return ExecutionDecision(
            decision="deny",
            classification="policy_inactive",
            reasons=["execution policy is not active"],
        )

    # Parse compound command
    plan = parse_compound(command)
    normalized = normalize_for_policy(plan, approved_scratch_dir=scratch_dir)

    # If parser confidence is too low, escalate
    if normalized.confidence < 0.4:
        return ExecutionDecision(
            decision="request_approval",
            classification="low_confidence",
            reasons=["parser confidence too low for automatic execution"]
                    + normalized.warnings,
            normalized_plan=normalized,
            approval_request=_build_approval(
                policy, normalized, "Parser could not safely analyze this command"),
        )

    # Classify each atomic action
    worst_tier = RiskTier.TIER_0_READ_ONLY
    all_reasons: List[str] = []
    all_classes: List[ActionClassification] = []

    for action in normalized.actions:
        cls = classify_command(action.command, policy)
        all_classes.append(cls)
        all_reasons.extend(cls.reasons)
        if cls.tier.value > worst_tier.value:
            worst_tier = cls.tier

    # Look up policy permission for the worst-tier action class
    worst_cls = max(all_classes, key=lambda c: c.tier.value)
    perm = policy.permission_for(worst_cls.action_class)

    # Tier 4 is always deny unless explicit override
    if worst_tier == RiskTier.TIER_4_EXTERNAL:
        return ExecutionDecision(
            decision="deny",
            classification=worst_tier.value,
            reasons=all_reasons + ["external/production action requires explicit authorization"],
            normalized_plan=normalized,
        )

    # Tier 3 with deny
    if worst_tier == RiskTier.TIER_3_HIGH_RISK and perm == ActionLevel.DENY:
        return ExecutionDecision(
            decision="deny",
            classification=worst_tier.value,
            reasons=all_reasons + [f"policy denies {worst_cls.action_class}"],
            normalized_plan=normalized,
        )

    # Map permission level to decision
    if perm == ActionLevel.DENY:
        return ExecutionDecision(
            decision="deny",
            classification=worst_tier.value,
            reasons=all_reasons + [f"policy denies {worst_cls.action_class}"],
            normalized_plan=normalized,
        )

    if perm == ActionLevel.AUTO:
        return ExecutionDecision(
            decision="auto_execute",
            classification=worst_tier.value,
            reasons=all_reasons + [f"policy auto-approves {worst_cls.action_class}"],
            normalized_plan=normalized,
        )

    if perm == ActionLevel.TASK_SCOPED:
        return ExecutionDecision(
            decision="allow_agent",
            classification=worst_tier.value,
            reasons=all_reasons + [f"policy allows {worst_cls.action_class} within task scope"],
            normalized_plan=normalized,
            policy_context=f"task {policy.scope.task_id} on branch {policy.scope.branch}",
        )

    # APPROVAL required
    return ExecutionDecision(
        decision="request_approval",
        classification=worst_tier.value,
        reasons=all_reasons + [f"policy requires approval for {worst_cls.action_class}"],
        normalized_plan=normalized,
        approval_request=_build_approval(policy, normalized,
                                         f"{worst_cls.action_class} requires approval"),
    )


def _build_approval(
    policy: ExecutionPolicy,
    plan: NormalizedPlan,
    summary: str,
) -> ApprovalRequest:
    """Build a structured approval request."""
    import re
    domains: List[str] = []
    write_locs: List[str] = []
    methods = ["GET"]  # default

    for action in plan.actions:
        url_match = re.search(r'https?://([^/\s"\']+)', action.command)
        if url_match:
            d = url_match.group(1).split(":")[0]
            if d not in domains:
                domains.append(d)
        output_match = re.search(r'-o\s+["\']?([^\s"\']+)', action.command)
        if output_match:
            p = output_match.group(1)
            if p not in write_locs:
                write_locs.append(p)
        if re.search(r"-X\s*(POST|PUT|DELETE|PATCH)", action.command, re.I):
            m = re.search(r"-X\s*(POST|PUT|DELETE|PATCH)", action.command, re.I)
            if m and m.group(1).upper() not in methods:
                methods.append(m.group(1).upper())

    return ApprovalRequest(
        task_id=policy.scope.task_id,
        summary=summary,
        action_count=len(plan.actions),
        domains=domains,
        methods=methods,
        write_locations=write_locs,
        expected_effects=["see normalized plan"],
    )


def batch_decisions(
    commands: List[str],
    policy: ExecutionPolicy,
    **kwargs,
) -> ExecutionDecision:
    """Batch multiple related commands into one approval request.

    If all commands are auto-approvable, returns auto_execute.
    If any requires approval, returns one consolidated request.
    If any is denied, returns deny.
    """
    individual = [decide(cmd, policy, **kwargs) for cmd in commands]

    # If any denied, deny all
    denied = [d for d in individual if d.decision == "deny"]
    if denied:
        return ExecutionDecision(
            decision="deny",
            classification="batch_denied",
            reasons=[f"batch contains {len(denied)} denied action(s)"]
                    + [r for d in denied for r in d.reasons],
        )

    # If all auto, batch auto
    if all(d.decision == "auto_execute" for d in individual):
        all_reasons = [r for d in individual for r in d.reasons]
        return ExecutionDecision(
            decision="auto_execute",
            classification="batch_auto",
            reasons=[f"all {len(individual)} actions auto-approved"] + all_reasons,
        )

    # Otherwise, batch approval
    import re
    domains: List[str] = []
    write_locs: List[str] = []
    for d in individual:
        if d.approval_request:
            for dom in d.approval_request.domains:
                if dom not in domains:
                    domains.append(dom)
            for wl in d.approval_request.write_locations:
                if wl not in write_locs:
                    write_locs.append(wl)

    return ExecutionDecision(
        decision="request_approval",
        classification="batch_approval",
        reasons=[f"batch of {len(individual)} actions requires approval"],
        approval_request=ApprovalRequest(
            task_id=policy.scope.task_id,
            summary=f"{len(commands)} related actions need approval",
            action_count=len(commands),
            domains=domains,
            write_locations=write_locs,
        ),
    )
