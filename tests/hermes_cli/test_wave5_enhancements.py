"""Unit tests for Wave 5 Strategic Enhancements: Customer Billing Engine, Security Audit Gatekeeper, Model Inventory Prober, and Journey Harvester."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    finance_db,
    inventory,
    journey,
    metered_billing,
    objectives_db,
    organization_db,
    security_audit,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    metered_billing.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave5Corp",
        purpose="Wave 5 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    return conn, org_id


def test_run_automated_customer_billing(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    meter_id = metered_billing.create_meter(
        conn,
        organization_id=org_id,
        name="api_calls",
        currency="USD",
        unit_price_microminor=10_000_000,  # $10.00 per unit (10,000,000 microminor)
        unit_name="calls",
    )

    metered_billing.record_usage(
        conn,
        meter_id=meter_id,
        customer_id="cust_101",
        quantity=5,
        idempotency_key="usage_wave5_001",
        evidence={"type": "api_log"},
    )

    res = metered_billing.run_automated_customer_billing(
        conn, organization_id=org_id, customer_id="cust_101"
    )

    assert res["organization_id"] == org_id
    assert res["customer_id"] == "cust_101"
    assert res["total_amount_minor"] == 50  # 5 units * 10 minor = 50 minor units ($0.50)
    assert len(res["billing_runs"]) == 1



def test_assert_supply_chain_security_admissible(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    comp = security_audit.Component(
        name="requests", version="2.31.0", ecosystem="PyPI", source="venv"
    )
    vuln = security_audit.Vulnerability(
        osv_id="GHSA-test-1234", severity="CRITICAL", summary="Test CRITICAL vulnerability"
    )
    finding = security_audit.Finding(component=comp, vuln=vuln)

    res = security_audit.assert_supply_chain_security_admissible(
        conn, organization_id=org_id, findings=[finding], max_allowed_severity="HIGH"
    )

    assert res["admissible"] is False
    assert len(res["violating_findings"]) == 1


def test_probe_model_inventory_health(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    health = inventory.probe_model_inventory_health(conn, organization_id=org_id)

    assert health["organization_id"] == org_id
    assert "status" in health
    assert "active_provider_count" in health


def test_harvest_company_journey_milestones(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    acc_id = finance_db.create_treasury_account(
        conn, organization_id=org_id, currency="USD", name="operating"
    )
    finance_db.record_entry(
        conn,
        account_id=acc_id,
        kind="deposit",
        amount_minor=25000,
        currency="USD",
        idempotency_key="dep_wave5_journey",
        evidence={"source": "capital"},
    )

    milestones = journey.harvest_company_journey_milestones(conn, organization_id=org_id)

    assert milestones["organization_id"] == org_id
    assert milestones["milestone_count"] >= 1
    assert any(m["category"] == "treasury" for m in milestones["milestones"])
