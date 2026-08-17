"""Unit tests for Wave 13 Strategic Enhancements: Enterprise Board Package Generator, ERP Webhook Streamer, VAT/GST Settlement Engine, and Employee Merit Promotion Engine."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    accounting_db,
    hiring_policy,
    objective_triggers,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    accounting_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    objective_triggers.ensure_schema(conn)
    hiring_policy.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave13Corp",
        purpose="Wave 13 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id


def test_generate_board_meeting_resolution_package(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    pkg = organization_db.generate_board_meeting_resolution_package(
        conn, organization_id=org_id, quarter="2026-Q3"
    )

    assert pkg["package_id"].startswith("board_")
    assert pkg["organization_id"] == org_id
    assert pkg["quarter"] == "2026-Q3"
    assert pkg["status"] == "certified"


def test_stream_corporate_event_webhook(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    evt = objective_triggers.stream_corporate_event_webhook(
        conn,
        organization_id=org_id,
        event_type="objective.completed",
        payload={"objective_id": "obj_w13"},
    )

    assert evt["event_id"].startswith("evt_")
    assert evt["organization_id"] == org_id
    assert evt["event_type"] == "objective.completed"
    assert evt["status"] == "delivered"


def test_calculate_and_remit_jurisdiction_vat_gst(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    vat = accounting_db.calculate_and_remit_jurisdiction_vat_gst(
        conn,
        organization_id=org_id,
        gross_amount_minor=10000,
        jurisdiction="EU",
        vat_rate_pct=20.0,
    )

    assert vat["remittance_id"].startswith("vat_")
    assert vat["organization_id"] == org_id
    assert vat["jurisdiction"] == "EU"
    assert vat["gross_amount_minor"] == 10000
    assert vat["vat_tax_minor"] == 2000
    assert vat["net_amount_minor"] == 8000
    assert vat["status"] == "remittance_provisioned"


def test_evaluate_employee_merit_promotion(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    prom = hiring_policy.evaluate_employee_merit_promotion(
        conn,
        organization_id=org_id,
        employee_id="emp_star_agent",
        verified_outcomes_count=5,
        net_yield_minor=100000,
    )

    assert prom["proposal_id"].startswith("prom_")
    assert prom["organization_id"] == org_id
    assert prom["employee_id"] == "emp_star_agent"
    assert prom["promotion_recommended"] is True
    assert prom["recommended_next_level"] == "manager"
    assert prom["status"] == "promotion_proposed"
