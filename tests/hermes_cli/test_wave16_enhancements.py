"""Unit tests for Wave 16 Strategic Enhancements: Executive Daily Briefing Generator, Cross-Region Data Residency Router, IP Patent Claim Harvester, and Vendor Dispute Chargeback Engine."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    accounting_db,
    journey,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    accounting_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave16Corp",
        purpose="Wave 16 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id


def test_generate_executive_daily_briefing_digest(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    brief = journey.generate_executive_daily_briefing_digest(conn, organization_id=org_id)

    assert brief["briefing_id"].startswith("brief_")
    assert brief["organization_id"] == org_id
    assert brief["period"] == "last_24_hours"
    assert brief["status"] == "ready_for_dispatch"


def test_assert_data_residency_sovereignty(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    sov = organization_db.assert_data_residency_sovereignty(
        conn, organization_id=org_id, target_region="eu-central-1"
    )

    assert sov["assertion_id"].startswith("sovereign_")
    assert sov["organization_id"] == org_id
    assert sov["target_region"] == "eu-central-1"
    assert sov["sovereignty_compliant"] is True
    assert sov["status"] == "sovereign_compliant"


def test_harvest_patentable_ip_claims(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    ip = journey.harvest_patentable_ip_claims(conn, organization_id=org_id)

    assert ip["harvest_id"].startswith("ip_")
    assert ip["organization_id"] == org_id
    assert ip["patentable_claims_count"] >= 1
    assert ip["status"] == "ip_claims_harvested"


def test_issue_vendor_sla_dispute_chargeback(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    disp = accounting_db.issue_vendor_sla_dispute_chargeback(
        conn,
        organization_id=org_id,
        vendor_id="vendor_faulty_cloud",
        breach_description="SLA Uptime Failure",
        claim_amount_minor=25000,
    )

    assert disp["dispute_id"].startswith("disp_")
    assert disp["organization_id"] == org_id
    assert disp["vendor_id"] == "vendor_faulty_cloud"
    assert disp["claim_amount_minor"] == 25000
    assert disp["status"] == "chargeback_filed"
