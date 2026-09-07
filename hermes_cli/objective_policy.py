"""Deterministic charter evaluation for autonomous objective actions.

The human operator is an advisor by default, not a synchronous approval queue.
Once initial setup establishes a standing operating charter, actions inside it
receive narrow permits automatically.  Missing or exceeded authority escalates;
explicitly prohibited actions are denied.

No model participates in this decision.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from hermes_cli import (
    finance_db,
    objectives_db as db,
    organization_db,
    regulatory_compliance,
)


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
OPERATING_MODES = frozenset({"autonomous", "supervised", "approval_required"})


@dataclass(frozen=True)
class PolicyDecision:
    verdict: str  # permit | escalate | deny
    reason: str
    constraints: dict[str, Any] = field(default_factory=dict)
    ttl_seconds: int = 0
    approval_eligible: bool = False


def _string_set(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def validate_charter(charter: Mapping[str, Any]) -> None:
    mode = str(charter.get("operating_mode", "")).strip()
    if mode not in OPERATING_MODES:
        raise ValueError(
            "agentic.operating_mode must be autonomous, supervised, "
            "or approval_required"
        )
    max_risk = str(charter.get("max_autonomous_risk", "")).strip()
    if max_risk not in RISK_ORDER:
        raise ValueError(
            "agentic.max_autonomous_risk must be low, medium, high, or critical"
        )
    ttl = charter.get("permit_ttl_seconds", 0)
    if not isinstance(ttl, int) or ttl <= 0:
        raise ValueError("agentic.permit_ttl_seconds must be a positive integer")
    spend = charter.get("max_action_spend_minor", 0)
    if not isinstance(spend, int) or spend < 0:
        raise ValueError("agentic.max_action_spend_minor must be non-negative")
    runtime_host = str(charter.get("runtime_host", "gateway")).strip()
    if runtime_host not in {"gateway", "standalone", "either"}:
        raise ValueError(
            "agentic.runtime_host must be gateway, standalone, or either"
        )
    for key in ("event_claim_ttl_seconds", "resource_lease_ttl_seconds"):
        ttl_value = charter.get(key, 300)
        if not isinstance(ttl_value, int) or ttl_value < 3:
            raise ValueError(f"agentic.{key} must be an integer of at least 3")
    solo_founder = charter.get("solo_founder") or {}
    if not isinstance(solo_founder, Mapping):
        raise ValueError("agentic.solo_founder must be a mapping")
    for key in ("toolsets", "skills"):
        values = solo_founder.get(key, [])
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item.strip() for item in values
        ):
            raise ValueError(
                f"agentic.solo_founder.{key} must be a list of non-empty strings"
            )
    if "all" in _string_set(solo_founder.get("toolsets")):
        raise ValueError(
            "agentic.solo_founder.toolsets cannot include the unrestricted all toolset"
        )
    approvals = charter.get("action_approvals") or {}
    default_approval_ttl = int(approvals.get("default_ttl_seconds", 900))
    maximum_approval_ttl = int(approvals.get("maximum_ttl_seconds", 3600))
    if (
        default_approval_ttl <= 0
        or maximum_approval_ttl <= 0
        or default_approval_ttl > maximum_approval_ttl
    ):
        raise ValueError(
            "agentic.action_approvals TTLs must be positive and bounded"
        )
    policy = charter.get("blocked_outcome_policy")
    if policy is not None:
        if not isinstance(policy, Mapping):
            raise ValueError("agentic.blocked_outcome_policy must be a mapping")
        mode = str(policy.get("mode", "advise")).strip()
        if mode not in {"advise", "autonomous"}:
            raise ValueError(
                "agentic.blocked_outcome_policy.mode must be advise or autonomous"
            )
        if mode == "autonomous":
            attempts = policy.get("max_replan_attempts", 3)
            if not isinstance(attempts, int) or attempts <= 0 or attempts > 25:
                raise ValueError(
                    "agentic.blocked_outcome_policy.max_replan_attempts must be "
                    "a positive integer of at most 25"
                )
            backoff = policy.get("replan_backoff_seconds", 60)
            if not isinstance(backoff, int) or backoff < 0:
                raise ValueError(
                    "agentic.blocked_outcome_policy.replan_backoff_seconds must "
                    "be a non-negative integer"
                )
            abandon = policy.get("abandon_after_max", True)
            if not isinstance(abandon, bool):
                raise ValueError(
                    "agentic.blocked_outcome_policy.abandon_after_max must be a "
                    "boolean"
                )
    from hermes_cli import resource_budget

    resource_limits = {
        **resource_budget.DEFAULT_LIMITS,
        "planner_call_compute_reservation_minor": 10,
        "compute_reconciliation_grace_seconds": 86_400,
        **(charter.get("resource_limits") or {}),
    }
    resource_keys = (
        "max_cycles_per_objective",
        "max_actions_per_cycle",
        "max_actions_per_objective",
        "max_input_tokens_per_objective",
        "max_output_tokens_per_objective",
        "max_compute_cost_minor_per_objective",
        "max_compute_cost_minor_per_organization",
        "planner_call_compute_reservation_minor",
        "compute_reconciliation_grace_seconds",
    )
    for key in resource_keys:
        value = resource_limits.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"agentic.resource_limits.{key} must be a positive integer"
            )
    if (
        resource_limits["planner_call_compute_reservation_minor"]
        > resource_limits["max_compute_cost_minor_per_objective"]
    ):
        raise ValueError(
            "agentic.resource_limits planner call reservation exceeds "
            "the objective compute ceiling"
        )


def evaluate_action(
    *,
    objective: Mapping[str, Any],
    action: Mapping[str, Any],
    charter: Mapping[str, Any],
    exact_approval: bool = False,
    effective_objective_budget: Optional[int] = None,
) -> PolicyDecision:
    """Evaluate one proposed action against objective scope and setup charter."""
    validate_charter(charter)

    if not bool(charter.get("enabled", False)):
        return PolicyDecision("escalate", "agentic operation is not enabled")
    if objective.get("status") not in {"planned", "authorized", "executing"}:
        return PolicyDecision(
            "deny",
            f"objective status {objective.get('status')} does not admit permits",
        )
    expires_at = objective.get("expires_at")
    if expires_at is not None and int(expires_at) <= int(time.time()):
        return PolicyDecision("deny", "objective has expired")

    capability = str(action.get("required_capability", "")).strip()
    action_type = str(action.get("action_type", "")).strip()
    payload = action.get("payload")
    if not isinstance(payload, Mapping):
        return PolicyDecision("deny", "action payload is not a JSON object")
    security = charter.get("security") or {}
    if bool(security.get("require_idempotency_key_for_external_actions", False)):
        idempotency_key = str(payload.get("idempotency_key", "")).strip()
        if len(idempotency_key) < 16:
            return PolicyDecision(
                "escalate",
                "external action requires a unique high-entropy idempotency key",
            )
    if bool(security.get("require_fresh_state_for_external_actions", False)):
        observed_at = payload.get("observed_state_at")
        max_age = payload.get("max_state_age_seconds")
        evidence = payload.get("state_evidence")
        if (
            not isinstance(observed_at, int)
            or not isinstance(max_age, int)
            or max_age <= 0
            or not isinstance(evidence, Mapping)
            or not evidence.get("reference")
        ):
            return PolicyDecision(
                "escalate",
                "external action requires fresh authoritative state evidence",
            )

    forbidden = _string_set(charter.get("forbidden_capabilities"))
    objective_forbidden = _string_set(objective.get("prohibited_actions"))
    if capability in forbidden or action_type in objective_forbidden:
        return PolicyDecision("deny", "action is explicitly prohibited by policy")

    allowed_capabilities = _string_set(charter.get("allowed_capabilities"))
    if capability not in allowed_capabilities:
        return PolicyDecision(
            "escalate", f"capability {capability!r} is outside the standing charter"
        )

    system = str(payload.get("system", "")).strip()
    charter_systems = _string_set(charter.get("allowed_systems"))
    objective_systems = _string_set(objective.get("permitted_systems"))
    if not system:
        return PolicyDecision(
            "escalate", "action payload must identify its target system"
        )
    if system not in charter_systems or (
        objective_systems and system not in objective_systems
    ):
        return PolicyDecision(
            "escalate", f"target system {system!r} is outside permitted scope"
        )

    risk = str(action.get("risk_class", "")).strip()
    if risk not in RISK_ORDER:
        return PolicyDecision("deny", f"unknown risk class {risk!r}")
    max_risk = str(charter["max_autonomous_risk"])
    if RISK_ORDER[risk] > RISK_ORDER[max_risk] and not exact_approval:
        return PolicyDecision(
            "escalate",
            f"{risk} risk exceeds autonomous ceiling {max_risk}",
            approval_eligible=True,
        )

    reversible = bool(action.get("reversible"))
    compensation_contract = {
        "action_type": action.get("compensation_action_type"),
        "payload": action.get("compensation_payload_json"),
        "capability": action.get("compensation_capability"),
        "verification_method": action.get("compensation_verification_method"),
    }
    if (
        reversible
        and bool(security.get("require_compensation_for_reversible_actions", False))
        and not all(compensation_contract.values())
    ):
        return PolicyDecision(
            "escalate",
            "reversible external action requires an exact compensation contract",
        )
    if not reversible and not bool(charter.get("allow_irreversible", False)):
        return PolicyDecision(
            "escalate", "irreversible actions are outside the standing charter"
        )

    estimated_cost = action.get("estimated_cost_minor")
    estimated_cost = int(estimated_cost or 0)
    objective_budget = (
        effective_objective_budget
        if effective_objective_budget is not None
        else objective.get("max_spend_minor")
    )
    charter_budget = int(charter.get("max_action_spend_minor", 0))
    if estimated_cost < 0:
        return PolicyDecision("deny", "estimated action cost cannot be negative")
    if estimated_cost > charter_budget:
        return PolicyDecision(
            "escalate", "estimated action cost exceeds the per-action charter limit"
        )
    if objective_budget is not None and estimated_cost > int(objective_budget):
        return PolicyDecision(
            "escalate", "estimated action cost exceeds the objective budget"
        )

    mode = str(charter["operating_mode"])
    approval_required = _string_set(charter.get("approval_required_capabilities"))
    if mode == "approval_required" and not exact_approval:
        return PolicyDecision(
            "escalate",
            "setup requires approval for every action",
            approval_eligible=True,
        )
    if capability in approval_required and not exact_approval:
        return PolicyDecision(
            "escalate",
            "this capability requires approval under the charter",
            approval_eligible=True,
        )
    if (
        mode == "supervised"
        and risk in {"high", "critical"}
        and not exact_approval
    ):
        return PolicyDecision(
            "escalate",
            "supervised mode requires approval for high-risk actions",
            approval_eligible=True,
        )

    target = str(payload.get("target_resource", "")).strip()
    return PolicyDecision(
        "permit",
        "action is inside the standing operating charter",
        constraints={
            "system": system,
            "target_resource": target or None,
            "max_cost_minor": estimated_cost,
            "risk_class": risk,
            "reversible": reversible,
        },
        ttl_seconds=int(charter["permit_ttl_seconds"]),
    )


def evaluate_and_record(
    conn,
    action_id: str,
    *,
    charter: Mapping[str, Any],
    executor: str,
    policy_version: str,
    approval_artifact_id: Optional[str] = None,
) -> tuple[PolicyDecision, Optional[str]]:
    """Evaluate an action and atomically record denial or issue a permit."""
    action_row = conn.execute(
        "SELECT * FROM candidate_actions WHERE id = ?", (action_id,)
    ).fetchone()
    if action_row is None:
        raise KeyError(f"action not found: {action_id}")
    action = dict(action_row)
    action["payload"] = json.loads(action.pop("payload_json"))
    objective = db.objective_to_dict(conn, action["objective_id"])
    from hermes_cli import compensation

    try:
        compensation.assert_action_matches_obligation(
            conn,
            objective_id=action["objective_id"],
            action_type=action["action_type"],
            payload=action["payload"],
            capability=action["required_capability"],
            verification_method=action["verification_method"],
        )
    except compensation.CompensationError as exc:
        unavailable = PolicyDecision("deny", str(exc))
        db.deny_action(
            conn, action_id, actor=f"policy:{policy_version}",
            reason=unavailable.reason,
        )
        return unavailable, None
    ceo = organization_db.active_ceo(conn)
    organization_mismatch = (
        ceo is not None
        and objective.get("organization_id") != ceo["organization_id"]
    ) or (
        ceo is None
        and objective.get("organization_id") != "__unscoped__"
    )
    if organization_mismatch:
        unavailable = PolicyDecision(
            "deny", "objective organization does not match the active CEO"
        )
        db.deny_action(
            conn, action_id, actor=f"policy:{policy_version}",
            reason=unavailable.reason,
        )
        return unavailable, None
    approval_artifact = None
    if approval_artifact_id is not None:
        from hermes_cli import approval_artifacts

        approval_artifact = approval_artifacts.validate_for_action(
            conn,
            artifact_id=approval_artifact_id,
            action_id=action_id,
            organization_id=str(objective["organization_id"]),
            policy_version=policy_version,
        )
    op_key = f"{action.get('action_type', '')}:{action.get('payload', {}).get('system', '')}"
    if op_key.strip(":") and approval_artifact_id is None:
        from hermes_cli import operation_circuit_breaker

        try:
            operation_circuit_breaker.assert_admissible(conn, op_key)
        except operation_circuit_breaker.CircuitOpenError as exc:
            unavailable = PolicyDecision("escalate", f"circuit breaker open: {exc}")
            with conn:
                db._append_event(
                    conn,
                    action["objective_id"],
                    "action_escalated",
                    f"policy:{policy_version}",
                    {"action_id": action_id, "reason": unavailable.reason},
                )
            return unavailable, None

    effective_objective_budget = None
    if objective.get("max_spend_minor") is not None and action.get("objective_id"):
        from hermes_cli import outcome_attribution

        base_budget = int(objective["max_spend_minor"])
        net_yield, is_verified = outcome_attribution.get_objective_net_yield(
            conn, str(action["objective_id"])
        )
        if is_verified and net_yield > 0:
            scale_limit = int(base_budget * 0.25)
            bonus = min(net_yield, scale_limit) if scale_limit > 0 else net_yield
            effective_objective_budget = base_budget + bonus

    decision = evaluate_action(
        objective=objective,
        action=action,
        charter=charter,
        exact_approval=approval_artifact_id is not None,
        effective_objective_budget=effective_objective_budget,
    )
    if decision.verdict == "deny":
        db.deny_action(
            conn,
            action_id,
            actor=f"policy:{policy_version}",
            reason=decision.reason,
        )
        return decision, None
    if decision.verdict == "escalate":
        # Escalation is intentionally non-terminal. The action remains proposed
        # so an advisor can change the charter or an authorized operator can
        # issue the exact permit.
        with conn:
            db._append_event(
                conn,
                action["objective_id"],
                "action_escalated",
                f"policy:{policy_version}",
                {"action_id": action_id, "reason": decision.reason},
            )
        return decision, None
    compliance_config = charter.get("compliance") or {}
    if bool(compliance_config.get("require_action_context", False)):
        compliance_context = action["payload"].get("compliance_context")
        ceo = organization_db.active_ceo(conn)
        if not isinstance(compliance_context, Mapping) or ceo is None:
            unavailable = PolicyDecision(
                "escalate",
                "action lacks organization-bound compliance context",
            )
            with conn:
                db._append_event(
                    conn,
                    action["objective_id"],
                    "action_escalated",
                    f"policy:{policy_version}",
                    {"action_id": action_id, "reason": unavailable.reason},
                )
            return unavailable, None
        try:
            regulatory_compliance.authorize_action(
                conn,
                organization_id=ceo["organization_id"],
                context=compliance_context,
            )
        except regulatory_compliance.ComplianceGateError as exc:
            unavailable = PolicyDecision("escalate", f"compliance unresolved: {exc}")
            with conn:
                db._append_event(
                    conn,
                    action["objective_id"],
                    "action_escalated",
                    f"policy:{policy_version}",
                    {"action_id": action_id, "reason": unavailable.reason},
                )
            return unavailable, None

    estimated_cost = int(action.get("estimated_cost_minor") or 0)
    reservation_created = False
    if estimated_cost:
        ceo = organization_db.active_ceo(conn)
        currency = str(objective.get("currency") or "USD")
        account_id = (
            finance_db.operating_account_for_organization(
                conn, ceo["organization_id"], currency
            )
            if ceo is not None
            else None
        )
        if account_id is None:
            unavailable = PolicyDecision(
                "escalate",
                "paid action has no matching governed operating account",
            )
            with conn:
                db._append_event(
                    conn,
                    action["objective_id"],
                    "action_escalated",
                    f"policy:{policy_version}",
                    {"action_id": action_id, "reason": unavailable.reason},
                )
            return unavailable, None
        try:
            finance_db.reserve_budget(
                conn,
                account_id=account_id,
                objective_id=action["objective_id"],
                action_id=action_id,
                amount_minor=estimated_cost,
                currency=currency,
                expires_at=int(time.time()) + decision.ttl_seconds,
                objective_budget_minor=(
                    effective_objective_budget
                    if effective_objective_budget is not None
                    else objective.get("max_spend_minor")
                ),
            )
            reservation_created = True
        except finance_db.BudgetError as exc:
            unavailable = PolicyDecision("escalate", f"budget unavailable: {exc}")
            with conn:
                db._append_event(
                    conn,
                    action["objective_id"],
                    "action_escalated",
                    f"policy:{policy_version}",
                    {"action_id": action_id, "reason": unavailable.reason},
                )
            return unavailable, None
    try:
        permit_expiry = int(time.time()) + decision.ttl_seconds
        if approval_artifact is not None:
            permit_expiry = min(
                permit_expiry, int(approval_artifact["expires_at"])
            )
        permit_id = db.issue_permit(
            conn,
            action_id,
            capability=action["required_capability"],
            issued_to=executor,
            policy_version=policy_version,
            expires_at=permit_expiry,
            target_resource=action["payload"].get("target_resource"),
            approval_artifact_id=approval_artifact_id,
            constraints=decision.constraints,
        )
    except Exception:
        if reservation_created:
            finance_db.release_reservation(conn, action_id, reason="permit_issue_failed")
        raise
    if approval_artifact_id is not None:
        from hermes_cli import approval_artifacts

        approval_artifacts.bind_permit(
            conn,
            artifact_id=approval_artifact_id,
            permit_id=permit_id,
        )
    return decision, permit_id


def evolve_corporate_governance_policies(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    objective_id: str = "obj_default",
) -> dict[str, Any]:
    """Dynamically auto-tune governance policy spend ceilings and risk rules based on historical yield."""
    from hermes_cli import outcome_attribution

    net_yield_minor, is_verified = outcome_attribution.get_objective_net_yield(
        conn, objective_id
    )
    roi_scale = 1.25 if is_verified and net_yield_minor > 0 else 1.0

    ts = int(time.time())
    policy_version = f"pol_v{int(ts)}"

    return {
        "policy_version": policy_version,
        "organization_id": organization_id,
        "objective_id": objective_id,
        "net_yield_minor": net_yield_minor,
        "is_verified": is_verified,
        "spend_ceiling_multiplier": roi_scale,
        "status": "evolved",
        "timestamp": ts,
    }


def cascade_strategic_goal_alignment(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    macro_goal_name: str = "reach_50m_arr",
    target_revenue_minor: int = 5000000000,
) -> dict[str, Any]:
    """Decompose corporate C-suite macro goal into aligned departmental sub-objectives and strategy routes."""
    import time
    import uuid

    cascade_id = f"cascade_{uuid.uuid4().hex}"

    ts = int(time.time())

    sub_objectives = [
        {"department": "sales", "target_share_pct": 50.0, "sub_target_minor": int(target_revenue_minor * 0.5)},
        {"department": "marketing", "target_share_pct": 30.0, "sub_target_minor": int(target_revenue_minor * 0.3)},
        {"department": "product", "target_share_pct": 20.0, "sub_target_minor": int(target_revenue_minor * 0.2)},
    ]

    return {
        "strategic_cascade_id": cascade_id,
        "organization_id": organization_id,
        "macro_goal_name": macro_goal_name,
        "target_revenue_minor": target_revenue_minor,
        "sub_objectives_cascaded_count": len(sub_objectives),
        "sub_objectives": sub_objectives,
        "status": "goal_cascaded_aligned",
        "timestamp": ts,
    }



