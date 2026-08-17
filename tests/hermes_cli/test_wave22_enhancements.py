"""Unit tests for Wave 22 Strategic Enhancements: Revolving Credit Engine, Escrow Settlement Engine, Swarm Failover Prober, and SOP Version Auditor."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_commitments,
    finance_db,
    objectives_db,
    operational_control,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_commitments.ensure_schema(conn)
    finance_db.ensure_schema(conn)
    operational_control.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave22Corp",
        purpose="Wave 22 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id


def test_execute_revolving_credit_facility_drawdown(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    draw = finance_db.execute_revolving_credit_facility_drawdown(
        conn,
        organization_id=org_id,
        facility_id="fac_svb_revolver",
        drawdown_amount_minor=2500000,
        interest_rate_bps=650,
    )

    assert draw["credit_drawdown_id"].startswith("draw_")
    assert draw["organization_id"] == org_id
    assert draw["facility_id"] == "fac_svb_revolver"
    assert draw["drawdown_amount_minor"] == 2500000
    assert draw["status"] == "credit_facility_drawn"


def test_create_and_release_escrow_settlement(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    escrow = business_commitments.create_and_release_escrow_settlement(
        conn,
        organization_id=org_id,
        payee_id="vendor_acme_dev",
        escrow_amount_minor=1000000,
        verification_key="github.pr.merged",
    )

    assert escrow["escrow_settlement_id"].startswith("escrow_")
    assert escrow["organization_id"] == org_id
    assert escrow["payee_id"] == "vendor_acme_dev"
    assert escrow["escrow_released"] is True
    assert escrow["status"] == "escrow_payout_released"


def test_probe_agent_swarm_health_and_failover(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    failover = operational_control.probe_agent_swarm_health_and_failover(
        conn,
        organization_id=org_id,
        failed_agent_id="agent_outreach_2",
    )

    assert failover["swarm_failover_id"].startswith("failover_")
    assert failover["organization_id"] == org_id
    assert failover["failed_agent_id"] == "agent_outreach_2"
    assert failover["mandates_reassigned_count"] >= 1
    assert failover["status"] == "agent_swarm_healed"


def test_audit_sop_playbook_version_drift(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    drift = objectives_db.audit_sop_playbook_version_drift(
        conn,
        organization_id=org_id,
        playbook_id="sop_101",
    )

    assert drift["sop_drift_audit_id"].startswith("sopdrift_")
    assert drift["organization_id"] == org_id
    assert drift["playbook_id"] == "sop_101"
    assert drift["version_drift_detected_count"] == 0
    assert drift["status"] == "sop_version_aligned"
