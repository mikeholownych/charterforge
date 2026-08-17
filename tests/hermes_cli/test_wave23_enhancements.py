"""Unit tests for Wave 23 Strategic Enhancements: Multi-Tenant PII Masking Engine, ESOP Equity Granting Engine, Vendor Rate-Card Benchmarking Engine, and Cross-Boundary Mandate Revocation Engine."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    authority_bridge,
    hiring_policy,
    objectives_db,
    organization_db,
    procurement_policy,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    hiring_policy.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    procurement_policy.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave23Corp",
        purpose="Wave 23 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id


def test_enforce_multitenant_data_masking_policy(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    mask = organization_db.enforce_multitenant_data_masking_policy(
        conn,
        organization_id=org_id,
        payload_dict={
            "user_id": "usr_99",
            "email": "alice@wave23.com",
            "ssn": "000-12-3456",
            "action": "execute_task",
        },
    )

    assert mask["data_mask_id"].startswith("mask_")
    assert mask["organization_id"] == org_id
    assert mask["redacted_fields_count"] == 2
    assert mask["masked_payload"]["email"] == "***REDACTED***"
    assert mask["masked_payload"]["ssn"] == "***REDACTED***"
    assert mask["masked_payload"]["user_id"] == "usr_99"
    assert mask["status"] == "pii_masked"


def test_grant_employee_equity_options(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    esop = hiring_policy.grant_employee_equity_options(
        conn,
        organization_id=org_id,
        employee_id="emp_senior_lead",
        shares_granted=10000,
        strike_price_cents=100,
    )

    assert esop["equity_grant_id"].startswith("esop_")
    assert esop["organization_id"] == org_id
    assert esop["employee_id"] == "emp_senior_lead"
    assert esop["shares_granted"] == 10000
    assert esop["vesting_schedule"] == "4_year_1_year_cliff"
    assert esop["status"] == "equity_grant_issued"


def test_benchmark_vendor_ratecard_pricing(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    bench = procurement_policy.benchmark_vendor_ratecard_pricing(
        conn,
        organization_id=org_id,
        vendor_id="vendor_saas_crm",
        contracted_rate_cents=50000,
    )

    assert bench["ratecard_benchmark_id"].startswith("bench_")
    assert bench["organization_id"] == org_id
    assert bench["vendor_id"] == "vendor_saas_crm"
    assert bench["over_indexed"] is True
    assert bench["status"] == "rate_over_indexed_flagged"


def test_revoke_all_cross_entity_mandates(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    revocation = authority_bridge.revoke_all_cross_entity_mandates(
        conn,
        organization_id=org_id,
        reason="emergency_breach_containment",
    )

    assert revocation["revocation_id"].startswith("revocation_")
    assert revocation["organization_id"] == org_id
    assert revocation["reason"] == "emergency_breach_containment"
    assert revocation["bridges_revoked_count"] >= 1
    assert revocation["status"] == "cross_boundary_mandates_revoked"
