"""Unit tests for automated regulatory compliance deadline harvesting."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    accounting_db,
    compliance_deadlines,
    objectives_db,
    organization_db,
)


def test_harvest_jurisdiction_compliance_deadlines_provisions_obligations(tmp_path):
    conn = objectives_db.connect(tmp_path / "authority.db")
    accounting_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="ComplianceCorp",
        purpose="Tax compliance testing",
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
        purpose="Run compliance test",
        responsibilities=["compliance"],
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

    result = compliance_deadlines.harvest_jurisdiction_compliance_deadlines(
        conn,
        organization_id=org_id,
        jurisdiction="US-CA",
        year=2026,
    )

    assert result["jurisdiction"] == "US-CA"
    assert result["harvested_obligations"] == 4
    assert len(result["obligation_ids"]) == 4

    rows = conn.execute(
        "SELECT COUNT(*) AS total FROM tax_obligations WHERE organization_id=?",
        (org_id,),
    ).fetchone()
    assert int(rows["total"]) == 4
