"""Unit tests for Wave 18 Strategic Enhancements: Competitive Intelligence Tracker, Vendor Fragility Auditor, Capital Re-Allocation Engine, and Disaster Recovery Prober."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    authority_integrity,
    business_metrics,
    finance_db,
    objectives_db,
    organization_db,
    procurement_policy,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    authority_integrity.ensure_schema(conn)
    business_metrics.ensure_schema(conn)
    finance_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    procurement_policy.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="ParentCorpW18",
        purpose="Parent Wave 18 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    sub_id = organization_db.create_organization(
        conn,
        name="SubCorpW18",
        purpose="Sub Wave 18 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, sub_id


def test_track_competitor_market_intelligence_signals(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    intel = business_metrics.track_competitor_market_intelligence_signals(
        conn, organization_id=parent_id, competitor_name="AcmeCorp"
    )

    assert intel["signal_id"].startswith("intel_")
    assert intel["organization_id"] == parent_id
    assert intel["competitor_name"] == "AcmeCorp"
    assert intel["status"] == "market_signal_logged"


def test_audit_supply_chain_vendor_fragility(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    frag = procurement_policy.audit_supply_chain_vendor_fragility(
        conn, organization_id=parent_id, vendor_id="vend_cloud_main"
    )

    assert frag["audit_id"].startswith("fragility_")
    assert frag["organization_id"] == parent_id
    assert frag["vendor_id"] == "vend_cloud_main"
    assert frag["risk_grade"] == "A+"
    assert frag["status"] == "vendor_low_risk"


def test_reallocate_multientity_capital_portfolio(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    rebal = finance_db.reallocate_multientity_capital_portfolio(
        conn, parent_org_id=parent_id
    )

    assert rebal["rebalance_id"].startswith("rebal_")
    assert rebal["parent_org_id"] == parent_id
    assert rebal["transfers_executed_count"] == 1
    assert rebal["status"] == "portfolio_rebalanced"


def test_verify_disaster_recovery_replica_integrity(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    dr = authority_integrity.verify_disaster_recovery_replica_integrity(
        conn, organization_id=parent_id
    )

    assert dr["dr_probe_id"].startswith("drprobe_")
    assert dr["organization_id"] == parent_id
    assert dr["dr_replica_in_sync"] is True
    assert dr["status"] == "zero_data_loss_verified"
