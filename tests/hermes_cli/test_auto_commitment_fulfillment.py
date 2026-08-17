"""Unit tests for automated business commitment fulfillment and SLA deadline tracking."""

from __future__ import annotations

import sqlite3
import time

from hermes_cli import (
    business_commitments,
    objectives_db,
    organization_db,
    verification_evidence,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_commitments.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="CommitmentCorp",
        purpose="SLA tracking",
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
        purpose="Run SLA test",
        responsibilities=["SLAs"],
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
        desired_outcome="Deliver software release",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_auto_fulfill_commitments_from_verifications(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)
    now = int(time.time())

    cid, _ = business_commitments.create_commitment(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        kind="customer_delivery",
        title="Deliver v1.0 release PR",
        description="PR merge deliverable",
        counterparty_type="customer",
        counterparty_reference="client_acme",
        source_system="github",
        source_reference="owner/repo:pr:101",
        due_at=now + 86400,
        grace_seconds=3600,
        required_verifier="github.pr.merged",
        financial_exposure_minor=50000,
        currency="USD",
        idempotency_key="commit_deliver_v1_0_release",
        created_by="employee:ceo",
    )

    plan_id = objectives_db.create_plan(
        conn,
        obj_id,
        assumptions=[],
        tasks=[{"id": "t1"}],
        dependencies=[],
        risks=[],
        created_by="employee:ceo",
    )
    action_id = objectives_db.propose_action(
        conn,
        objective_id=obj_id,
        plan_id=plan_id,
        action_type="github.pr.merge",
        payload={
            "system": "github",
            "target_resource": "owner/repo",
            "idempotency_key": "123456789012345678",
        },
        expected_outcome="PR merged",
        required_capability="github.write",
        verification_method="github.pr.merged",
        risk_class="low",
        reversible=False,
        proposed_by="employee:ceo",
    )

    # Record passing verification evidence
    vid = objectives_db.record_verification(
        conn,
        objective_id=obj_id,
        organization_id=org_id,
        plan_id=plan_id,
        action_id=action_id,
        execution_result_id="exec_1",
        verifier="control:verification",
        method="github.pr.merged",
        verdict="pass",
        evidence=verification_evidence.build(
            observer="control:verification",
            source_kind="provider_readback",
            source_reference="github:owner/repo:pr:101",
            facts={"status": "merged", "merged": True},
        ),
    )

    fulfilled = business_commitments.auto_fulfill_commitments_from_verifications(
        conn, org_id
    )

    assert cid in fulfilled

    c = conn.execute(
        "SELECT status, fulfilment_verification_id FROM business_commitments WHERE id=?",
        (cid,),
    ).fetchone()
    assert c["status"] == "fulfilled"
    assert c["fulfilment_verification_id"] == vid


def test_check_upcoming_commitment_deadlines_flags_risk_and_breach(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)
    now = int(time.time())

    # Commitment due in 2 hours (at risk)
    cid_risk, _ = business_commitments.create_commitment(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        kind="service_level",
        title="API uptime SLA",
        description="Keep 99.9% uptime",
        counterparty_type="customer",
        counterparty_reference="client_corp",
        source_system="sla",
        source_reference="sla:999",
        due_at=now + 7200,
        grace_seconds=3600,
        required_verifier="http.response.200",
        financial_exposure_minor=10000,
        currency="USD",
        idempotency_key="commit_sla_uptime_999",
        created_by="employee:ceo",
    )

    # Commitment past due and past grace period (breached)
    cid_breach, _ = business_commitments.create_commitment(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        kind="financial",
        title="Pay invoice",
        description="Vendor payment",
        counterparty_type="vendor",
        counterparty_reference="vendor_hosting",
        source_system="payments",
        source_reference="inv_past_due",
        due_at=now - 7200,
        grace_seconds=1800,
        required_verifier="payments.provider_readback",
        financial_exposure_minor=20000,
        currency="USD",
        idempotency_key="commit_pay_past_due_inv",
        created_by="employee:ceo",
        now=now - 10000,
    )

    results = business_commitments.check_upcoming_commitment_deadlines(
        conn, org_id, warning_window_seconds=86400, now=now
    )

    at_risk_ids = [c["id"] for c in results["at_risk"]]
    breached_ids = [c["id"] for c in results["breached"]]

    assert cid_risk in at_risk_ids
    assert cid_breach in breached_ids

    c_breach = conn.execute(
        "SELECT status FROM business_commitments WHERE id=?", (cid_breach,)
    ).fetchone()
    assert c_breach["status"] == "breached"
