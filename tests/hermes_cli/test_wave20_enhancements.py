"""Unit tests for Wave 20 Strategic Enhancements: Channel Partner Engine, Proof-of-Reserves Auditor, P0 SWAT Dispatcher, and Compliance Policy Simulator."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    compliance_deadlines,
    finance_db,
    objectives_db,
    operational_control,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    operational_control.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave20Corp",
        purpose="Wave 20 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id


def test_register_and_authorize_channel_partner_tier(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    partner = organization_db.register_and_authorize_channel_partner_tier(
        conn,
        organization_id=org_id,
        partner_id="partner_acme_reseller",
        partner_name="Acme Reseller Ltd",
        partner_tier="Platinum",
    )

    assert partner["partner_auth_id"].startswith("partner_")
    assert partner["organization_id"] == org_id
    assert partner["partner_tier"] == "Platinum"
    assert partner["commission_pct"] == 20.0
    assert partner["status"] == "partner_authorized"


def test_audit_crosschain_treasury_proof_of_reserves(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    por = finance_db.audit_crosschain_treasury_proof_of_reserves(
        conn, organization_id=org_id, asset_symbol="USDC"
    )

    assert por["proof_of_reserves_id"].startswith("por_")
    assert por["organization_id"] == org_id
    assert por["asset_symbol"] == "USDC"
    assert por["proof_verified"] is True
    assert por["status"] == "reserves_cryptographically_verified"


def test_dispatch_p0_customer_outage_swat_response(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    swat = operational_control.dispatch_p0_customer_outage_swat_response(
        conn,
        organization_id=org_id,
        customer_id="cust_vip_enterprise",
        outage_severity="P0",
    )

    assert swat["swat_dispatch_id"].startswith("swat_")
    assert swat["organization_id"] == org_id
    assert swat["customer_id"] == "cust_vip_enterprise"
    assert swat["outage_severity"] == "P0"
    assert swat["status"] == "swat_swarm_deployed"


def test_simulate_compliance_policy_sandbox(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    sim = compliance_deadlines.simulate_compliance_policy_sandbox(
        conn, organization_id=org_id, policy_rules={"max_spend_limit": 50000}
    )

    assert sim["sandbox_simulation_id"].startswith("sandbox_")
    assert sim["organization_id"] == org_id
    assert sim["simulated_regulatory_breaches_count"] == 0
    assert sim["status"] == "sandbox_policy_admissible"
