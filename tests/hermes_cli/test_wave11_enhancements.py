"""Unit tests for Wave 11 Strategic Enhancements: Multi-Cloud DR Failover, Zero-Trust Threat Isolation, Corporate M&A Merger, and Context Token Compression."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    objectives_db,
    operational_control,
    organization_db,
    resource_budget,
    runtime_drift,
    security_audit,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    operational_control.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    runtime_drift.ensure_schema(conn)
    resource_budget.ensure_schema(conn)


    target_id = organization_db.create_organization(
        conn,
        name="TargetCorpW11",
        purpose="Target Wave 11 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    acquiring_id = organization_db.create_organization(
        conn,
        name="AcquiringCorpW11",
        purpose="Acquiring Wave 11 testing",
        operator_role="advisor",
        headcount_limit=20,
        payroll_budget_minor=200000,
    )

    return conn, target_id, acquiring_id


def test_failover_substrate_cloud_provider(tmp_path):
    conn, target_id, _ = _setup_test_db(tmp_path)

    res = runtime_drift.failover_substrate_cloud_provider(
        conn, organization_id=target_id, primary_backend="modal", failover_backend="daytona"
    )

    assert res["migration_id"].startswith("mig_")
    assert res["organization_id"] == target_id
    assert res["primary_backend"] == "modal"
    assert res["failover_backend"] == "daytona"
    assert res["status"] == "failed_over"


def test_detect_and_isolate_anomaly_threat(tmp_path):
    conn, target_id, _ = _setup_test_db(tmp_path)

    res = security_audit.detect_and_isolate_anomaly_threat(
        conn,
        organization_id=target_id,
        actor_id="employee:rogue_agent",
        action_kind="unauthorized_treasury_drain",
    )

    assert res["organization_id"] == target_id
    assert res["actor_id"] == "employee:rogue_agent"
    assert res["threat_detected"] is True
    assert res["quarantined"] is True
    assert res["status"] == "quarantined"
    assert res["intervention_id"].startswith("intervention_")


def test_execute_autonomous_corporate_merger(tmp_path):
    conn, target_id, acquiring_id = _setup_test_db(tmp_path)

    emp_id = organization_db.propose_employee(
        conn,
        organization_id=target_id,
        display_name="CEO Target",
        title="CEO",
        level="ceo",
        manager_id=None,
        proposed_by="setup:user",
    )



    res = organization_db.execute_autonomous_corporate_merger(
        conn, target_org_id=target_id, acquiring_org_id=acquiring_id
    )

    assert res["merger_id"].startswith("merger_")
    assert res["target_org_id"] == target_id
    assert res["acquiring_org_id"] == acquiring_id
    assert res["transferred_employees_count"] == 1
    assert res["status"] == "merged"

    # Verify employee organization update
    emp = conn.execute("SELECT organization_id FROM employees WHERE id = ?", (emp_id,)).fetchone()
    assert str(emp["organization_id"]) == acquiring_id


def test_compress_corporate_conversation_context(tmp_path):
    conn, target_id, _ = _setup_test_db(tmp_path)

    res = resource_budget.compress_corporate_conversation_context(
        conn,
        organization_id=target_id,
        session_id="session_long_w11",
        history_token_count=16000,
        max_target_tokens=4000,
    )

    assert res["session_id"] == "session_long_w11"
    assert res["organization_id"] == target_id
    assert res["initial_tokens"] == 16000
    assert res["compressed_tokens"] == 4000
    assert res["token_savings_pct"] == 75.0
    assert res["compressed"] is True
    assert res["status"] == "compressed"
