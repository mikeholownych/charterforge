"""Unit tests for self-healing permit circuit breakers in objective_policy."""

from __future__ import annotations

import sqlite3
from typing import Any

from hermes_cli import (
    objective_policy,
    objectives_db,
    operation_circuit_breaker,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    organization_db.ensure_schema(conn)
    operation_circuit_breaker.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="BreakerCorp",
        purpose="Circuit testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    ceo_id = organization_db.propose_employee(
        conn,
        organization_id=org_id,
        display_name="CEO",
        title="CEO",
        level="ceo",
        manager_id=None,
        proposed_by="setup:user",
    )
    organization_db.transition_employee(conn, ceo_id, "approved", actor="setup:user")
    organization_db.transition_employee(conn, ceo_id, "provisioning", actor="setup:user")
    organization_db.create_mandate(
        conn,
        ceo_id,
        purpose="Run tests",
        responsibilities=["tests"],
        decision_rights=["execute"],
        prohibited_actions=[],
        capabilities=["objectives.manage"],
        systems=["objectives"],
        kpis=[],
        escalation={},
        budget_minor=100000,
        expires_at=None,
        created_by="setup:user",
    )
    organization_db.transition_employee(conn, ceo_id, "active", actor="setup:user", profile_name="ceo")

    return conn, org_id


def _charter() -> dict[str, Any]:
    return {
        "enabled": True,
        "operating_mode": "autonomous",
        "max_autonomous_risk": "high",
        "permit_ttl_seconds": 300,
        "max_action_spend_minor": 5000,
        "allowed_capabilities": ["payments.execute", "test.capability"],
        "allowed_systems": ["failing_system"],
        "solo_founder": {"toolsets": ["cli"], "skills": []},
    }


def test_open_circuit_breaker_escalates_permit_evaluation(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    obj = objectives_db.create_objective(
        conn,
        desired_outcome="Test Circuit Breaker",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    plan_id = objectives_db.create_plan(
        conn,
        obj.id,
        assumptions=[],
        tasks=[{"id": "t1"}],
        dependencies=[],
        risks=[],
        created_by="employee:ceo",
    )

    action_id = objectives_db.propose_action(
        conn,
        objective_id=obj.id,
        plan_id=plan_id,
        action_type="test_action",
        payload={
            "system": "failing_system",
            "target_resource": "res_1",
            "idempotency_key": "123456789012345678",
        },
        expected_outcome="outcome",
        required_capability="test.capability",
        verification_method="deterministic_check",
        risk_class="low",
        reversible=True,
        estimated_cost_minor=100,
        proposed_by="employee:ceo",
    )

    # Trip the circuit breaker for operation_key 'test_action:failing_system'
    op_key = "test_action:failing_system"
    for _ in range(3):
        operation_circuit_breaker.record_outcome(
            conn,
            operation_key=op_key,
            succeeded=False,
            failure_threshold=3,
            cooldown_seconds=900,
            error="Remote system timeout",
        )

    decision, permit_id = objective_policy.evaluate_and_record(
        conn,
        action_id=action_id,
        charter=_charter(),
        executor="employee:ceo",
        policy_version="v1",
    )

    assert decision.verdict == "escalate"
    assert "circuit breaker open" in decision.reason
    assert permit_id is None
