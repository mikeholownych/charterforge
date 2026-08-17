"""Unit tests for Wave 4 Strategic Enhancements: Procurement Evaluator, Saga Rollback Dispatcher, Drift Auto-Healer, and Governed Email Dispatcher."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    company_email,
    compensation,
    finance_db,
    objectives_db,
    organization_db,
    procurement_policy,
    runtime_drift,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    procurement_policy.ensure_schema(conn)
    compensation.ensure_schema(conn)
    runtime_drift.ensure_schema(conn)
    company_email.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave4Corp",
        purpose="Wave 4 testing",
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
        purpose="Run wave 4 tests",
        responsibilities=["wave4"],
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
        desired_outcome="Build new infrastructure",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_auto_evaluate_procurement_case(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    acc_id = finance_db.create_treasury_account(
        conn, organization_id=org_id, currency="USD", name="operating"
    )
    finance_db.record_entry(
        conn,
        account_id=acc_id,
        kind="deposit",
        amount_minor=50000,
        currency="USD",
        idempotency_key="dep_wave4_procure",
        evidence={"source": "capital_injection"},
    )

    decision_id, decision = procurement_policy.auto_evaluate_procurement_case(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        service_name="CloudDatabase",
        estimated_cost_minor=300,
    )

    assert decision_id.startswith("procurement_")
    assert decision.choice in {"existing", "foss", "build", "buy", "defer"}


def test_dispatch_saga_compensations(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    obligations = compensation.dispatch_saga_compensations(conn, org_id)

    assert isinstance(obligations, list)


def test_probe_and_auto_rebaseline_runtime_drift(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    posture = runtime_drift.probe_and_auto_rebaseline_runtime_drift(
        conn,
        organization_id=org_id,
        charter={"enabled": True, "mode": "autonomous"},
    )

    assert posture.ready is True


def test_dispatch_governed_email_with_proof(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    receipt = company_email.dispatch_governed_email_with_proof(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        recipient="client@acme.com",
        subject="Monthly Service Report",
        body="Attached is the SLA uptime report for July.",
    )

    assert receipt["operation_id"].startswith("email_")
    assert receipt["recipient"] == "client@acme.com"
    assert receipt["status"] == "sent"
    assert len(receipt["subject_sha256"]) == 64
