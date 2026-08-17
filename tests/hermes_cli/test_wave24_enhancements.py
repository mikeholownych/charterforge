"""Unit tests for Wave 24 Strategic Enhancements: Subsidiary Dividend Engine, Customer Credit Risk Monitor, Agent Knowledge Retention Engine, and Multi-Region DR Traffic Router."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    finance_db,
    journey,
    metered_billing,
    objectives_db,
    organization_db,
    runtime_drift,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    metered_billing.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    runtime_drift.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="ParentCorpW24",
        purpose="Parent Wave 24 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    sub_id = organization_db.create_organization(
        conn,
        name="SubCorpW24",
        purpose="Subsidiary Wave 24 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, sub_id


def test_execute_subsidiary_dividend_distribution(tmp_path):
    conn, parent_id, sub_id = _setup_test_db(tmp_path)

    div = finance_db.execute_subsidiary_dividend_distribution(
        conn,
        organization_id=sub_id,
        parent_org_id=parent_id,
        dividend_amount_minor=1000000,
    )

    assert div["dividend_distribution_id"].startswith("dividend_")
    assert div["subsidiary_org_id"] == sub_id
    assert div["parent_org_id"] == parent_id
    assert div["dividend_amount_minor"] == 1000000
    assert div["status"] == "dividend_repatriated"


def test_monitor_customer_credit_risk_and_adjust_limits(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    risk = metered_billing.monitor_customer_credit_risk_and_adjust_limits(
        conn, organization_id=parent_id, customer_id="cust_enterprise_1"
    )

    assert risk["credit_risk_monitoring_id"].startswith("risk_")
    assert risk["organization_id"] == parent_id
    assert risk["customer_id"] == "cust_enterprise_1"
    assert risk["credit_score"] == 750
    assert risk["status"] == "credit_limit_adjusted"


def test_archive_and_index_agent_knowledge_base(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    kb = journey.archive_and_index_agent_knowledge_base(
        conn, organization_id=parent_id, agent_id="agent_outreach_1"
    )

    assert kb["knowledge_archive_id"].startswith("kb_")
    assert kb["organization_id"] == parent_id
    assert kb["agent_id"] == "agent_outreach_1"
    assert kb["trajectories_archived_count"] >= 1
    assert kb["status"] == "knowledge_archived_and_indexed"


def test_failover_disaster_recovery_traffic_region(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    failover = runtime_drift.failover_disaster_recovery_traffic_region(
        conn,
        organization_id=parent_id,
        failed_region="us-east-1",
        target_region="us-west-2",
    )

    assert failover["dr_traffic_failover_id"].startswith("drfailover_")
    assert failover["organization_id"] == parent_id
    assert failover["failed_region"] == "us-east-1"
    assert failover["target_region"] == "us-west-2"
    assert failover["traffic_rerouted_pct"] == 100.0
    assert failover["status"] == "dr_traffic_failed_over"
