"""Unit tests for hierarchical capacity and skill gap mining."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    hiring_policy,
    objectives_db,
    organization_db,
)


def test_capacity_miner_identifies_capability_gap_and_evaluates_hiring_decision(tmp_path):
    conn = objectives_db.connect(tmp_path / "authority.db")
    hiring_policy.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="GrowthCorp",
        purpose="Automated scaling",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=500000,
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
        purpose="Run growth",
        responsibilities=["growth"],
        decision_rights=["hire"],
        prohibited_actions=[],
        capabilities=["objectives.manage"],
        systems=["objectives"],
        kpis=["revenue"],
        escalation={},
        budget_minor=500000,
        expires_at=None,
        created_by="setup:user",
    )
    organization_db.transition_employee(conn, ceo_id, "active", actor="setup:user", profile_name="ceo")

    obj = objectives_db.create_objective(
        conn,
        desired_outcome="Expand marketing campaign",
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

    # Propose an action requiring missing capability 'marketing.ads.create'
    action_id = objectives_db.propose_action(
        conn,
        objective_id=obj.id,
        plan_id=plan_id,
        action_type="ads.create",
        payload={
            "system": "ads",
            "target_resource": "campaign_1",
            "idempotency_key": "123456789012345678",
        },
        expected_outcome="ads created",
        required_capability="marketing.ads.create",
        verification_method="deterministic_check",
        risk_class="low",
        reversible=True,
        estimated_cost_minor=500,
        proposed_by="employee:ceo",
    )

    # Mark objective as blocked due to missing capability
    objectives_db.transition_objective(
        conn,
        obj.id,
        "blocked",
        actor="employee:ceo",
        reason="missing capability marketing.ads.create",
    )

    decisions = hiring_policy.analyze_capacity_and_mine_skill_gaps(
        conn,
        organization_id=org_id,
    )

    assert len(decisions) >= 1
    decision_id, decision = decisions[0]
    assert decision_id.startswith("hiring_decision_")
    assert decision.verdict in {"hire", "defer", "deny"}
