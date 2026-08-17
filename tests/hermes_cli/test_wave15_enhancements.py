"""Unit tests for Wave 15 Strategic Enhancements: Sovereign Signature Verifier, SOC 2 Evidence Exporter, Multi-Tenant Quota Isolator, and Entity Liquidation Engine."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    authority_integrity,
    compliance_deadlines,
    finance_db,
    objectives_db,
    organization_db,
    resource_budget,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    authority_integrity.ensure_schema(conn)
    finance_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    resource_budget.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="ParentCorpW15",
        purpose="Parent Wave 15 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    sub_id = organization_db.create_organization(
        conn,
        name="SubCorpW15",
        purpose="Sub Wave 15 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, sub_id


def test_verify_sovereign_identity_signature(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    ver = authority_integrity.verify_sovereign_identity_signature(
        conn,
        organization_id=parent_id,
        actor_id="emp_ceo",
        message_hash="hash_msg_101",
        signature_hex="a1b2c3d4e5f678901234567890abcdef",
    )

    assert ver["verification_id"].startswith("sigver_")
    assert ver["organization_id"] == parent_id
    assert ver["actor_id"] == "emp_ceo"
    assert ver["signature_valid"] is True
    assert ver["status"] == "verified_sovereign"


def test_export_soc2_compliance_evidence_package(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    pkg = compliance_deadlines.export_soc2_compliance_evidence_package(
        conn, organization_id=parent_id, audit_period="2026-Q1-Q4"
    )

    assert pkg["export_package_id"].startswith("soc2_")
    assert pkg["organization_id"] == parent_id
    assert pkg["audit_period"] == "2026-Q1-Q4"
    assert "CC6.1" in pkg["control_criteria_mapped"]
    assert pkg["status"] == "soc2_package_exported"


def test_enforce_multitenant_resource_quota_limits(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    quota = resource_budget.enforce_multitenant_resource_quota_limits(
        conn, organization_id=parent_id, compute_units_requested=50, monthly_quota_limit=1000
    )

    assert quota["quota_id"].startswith("quota_")
    assert quota["organization_id"] == parent_id
    assert quota["compute_units_requested"] == 50
    assert quota["monthly_quota_limit"] == 1000
    assert quota["quota_admissible"] is True
    assert quota["status"] == "quota_granted"


def test_execute_autonomous_entity_liquidation(tmp_path):
    conn, parent_id, sub_id = _setup_test_db(tmp_path)

    liq = finance_db.execute_autonomous_entity_liquidation(
        conn,
        organization_id=parent_id,
        liquidating_org_id=sub_id,
        parent_treasury_acc="acc_parent_main",
    )

    assert liq["liquidation_id"].startswith("liq_")
    assert liq["organization_id"] == parent_id
    assert liq["liquidating_org_id"] == sub_id
    assert liq["status"] == "dissolved"

    # Verify organization headcount limit and payroll budget zeroed out
    org = conn.execute("SELECT headcount_limit, payroll_budget_minor FROM organizations WHERE id = ?", (sub_id,)).fetchone()
    assert org["headcount_limit"] == 0
    assert org["payroll_budget_minor"] == 0

