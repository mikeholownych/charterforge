"""Unit tests for automated compliance and tax evidence harvester."""

from __future__ import annotations

import sqlite3
import time

import pytest

from hermes_cli import accounting_db, objectives_db, organization_db


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    accounting_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Global Corp",
        purpose="Cross-border commerce",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    return conn, org_id


def test_harvest_tax_rule_provisions_registration_and_rate(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)
    now = int(time.time())

    reg_id, rate_id = accounting_db.harvest_tax_rule(
        conn,
        organization_id=org_id,
        jurisdiction="US-CA",
        occurred_at=now,
    )

    assert reg_id.startswith("taxreg_")
    assert rate_id.startswith("taxrate_")

    reg = conn.execute(
        "SELECT * FROM tax_registrations WHERE id=?", (reg_id,)
    ).fetchone()
    assert reg["jurisdiction"] == "US-CA"
    assert reg["tax_type"] == "sales_tax"
    assert reg["status"] == "active"

    rate = conn.execute("SELECT * FROM tax_rates WHERE id=?", (rate_id,)).fetchone()
    assert rate["rate_basis_points"] == 725  # 7.25% CA tax
    assert rate["authority_source"] == "harvested:jurisdiction_lookup:v1"


def test_calculate_tax_auto_harvest_unmapped_jurisdiction(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)
    now = int(time.time())

    # Unmapped jurisdiction 'GB' with auto_harvest=True
    amount_minor, rate_id = accounting_db.calculate_tax(
        conn,
        organization_id=org_id,
        jurisdiction="GB",
        tax_type="vat",
        tax_code="STANDARD",
        taxable_minor=10000,  # £100.00
        occurred_at=now,
        auto_harvest=True,
    )

    # 20% UK VAT on £100.00 = £20.00 (2000 minor)
    assert amount_minor == 2000
    assert rate_id.startswith("taxrate_")


def test_calculate_tax_auto_harvest_default_zero_rate_for_unknown(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)
    now = int(time.time())

    amount_minor, rate_id = accounting_db.calculate_tax(
        conn,
        organization_id=org_id,
        jurisdiction="ZZ-UNMAPPED",
        tax_type="sales_tax",
        tax_code="STANDARD",
        taxable_minor=5000,
        occurred_at=now,
        auto_harvest=True,
    )

    # Default rate for unmapped cross-border jurisdiction is 0 bps
    assert amount_minor == 0
    assert rate_id.startswith("taxrate_")
