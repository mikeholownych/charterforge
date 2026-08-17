"""Unit tests for Wave 6 Strategic Enhancements: SOP Synthesizer, Cadence Scheduler, Capacity Rebalancer, and Sub-Entity Replication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid

from hermes_cli import (
    finance_db,
    objective_triggers,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    objective_triggers.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave6Corp",
        purpose="Wave 6 testing",
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
        purpose="Run wave 6 tests",
        responsibilities=["wave6"],
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

    obj = objectives_db.create_objective(
        conn,
        desired_outcome="Automate customer onboarding",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_synthesize_sop_playbook_from_objective(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    plan_id = objectives_db.create_plan(
        conn,
        objective_id=obj_id,
        assumptions=["assump"],
        tasks=["task1"],
        dependencies=[],
        risks=[],
        created_by="employee:ceo",
    )
    act_id = f"act_{uuid.uuid4().hex}"
    payload_str = json.dumps({"customer_id": "cust_wave6"})
    payload_sha = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    conn.execute(
        """INSERT INTO candidate_actions
           (id, objective_id, plan_id, action_type, payload_json, payload_sha256, expected_outcome,
            required_capability, verification_method, risk_class, reversible, status,
            proposed_by, created_at, updated_at)
           VALUES (?, ?, ?, 'customer.onboard', ?, ?, 'onboarded', 'customers.manage',
                   'http.response.200', 'low', 1, 'verified', 'employee:ceo', 100, 100)""",
        (act_id, obj_id, plan_id, payload_str, payload_sha),
    )
    conn.commit()


    sop = objectives_db.synthesize_sop_playbook_from_objective(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        sop_name="CustomerOnboardingSOP",
    )

    assert sop["sop_id"].startswith("sop_")
    assert sop["organization_id"] == org_id
    assert sop["sop_name"] == "CustomerOnboardingSOP"
    assert sop["step_count"] == 1
    assert "customers.manage" in sop["capabilities_required"]



def test_schedule_recurring_business_cadence(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    sched_id = objective_triggers.schedule_recurring_business_cadence(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        event_type="billing_run",
        interval_seconds=86400,
    )

    assert sched_id.startswith("schedule_")


def test_rebalance_organizational_capacity(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    res = organization_db.rebalance_organizational_capacity(
        conn, organization_id=org_id
    )

    assert res["organization_id"] == org_id
    assert res["rebalanced"] is True
    assert res["active_employees"] >= 1


def test_replicate_sub_entity_organization(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    sub_org_id = organization_db.replicate_sub_entity_organization(
        conn,
        parent_org_id=org_id,
        entity_name="Wave6_EMEA_Franchise",
        headcount_limit=15,
        payroll_budget_minor=200000,
    )

    assert sub_org_id != org_id
    assert sub_org_id.startswith("org_")
