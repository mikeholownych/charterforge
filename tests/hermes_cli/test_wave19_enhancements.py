"""Unit tests for Wave 19 Strategic Enhancements: Contract Lifecycle Manager, Treasury Yield Optimizer, Statutory Annual Filing Dispatcher, and Agent Alignment Auditor."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_commitments,
    compliance_deadlines,
    finance_db,
    objectives_db,
    organization_db,
    security_audit,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_commitments.ensure_schema(conn)
    finance_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)


    org_id = organization_db.create_organization(
        conn,
        name="Wave19Corp",
        purpose="Wave 19 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id


def test_probe_contract_lifecycle_expirations(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    probe = business_commitments.probe_contract_lifecycle_expirations(
        conn, organization_id=org_id, window_days=30
    )

    assert probe["contract_probe_id"].startswith("contract_")
    assert probe["organization_id"] == org_id
    assert probe["expiration_window_days"] == 30
    assert probe["status"] == "contracts_monitored"


def test_optimize_treasury_cash_reserve_yield(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    yield_opt = finance_db.optimize_treasury_cash_reserve_yield(
        conn, organization_id=org_id, min_yield_bps=450
    )

    assert yield_opt["yield_optimization_id"].startswith("yield_")
    assert yield_opt["organization_id"] == org_id
    assert yield_opt["min_target_yield_bps"] == 450
    assert yield_opt["status"] == "yield_permit_issued"


def test_dispatch_statutory_annual_corporate_filing(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    filing = compliance_deadlines.dispatch_statutory_annual_corporate_filing(
        conn, organization_id=org_id, jurisdiction="DELAWARE_USA"
    )

    assert filing["filing_id"].startswith("corpfile_")
    assert filing["organization_id"] == org_id
    assert filing["jurisdiction"] == "DELAWARE_USA"
    assert filing["status"] == "annual_filing_dispatched"


def test_evaluate_agent_swarm_behavioral_alignment(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    align = security_audit.evaluate_agent_swarm_behavioral_alignment(
        conn, organization_id=org_id, agent_id="agent_outreach_1"
    )

    assert align["evaluation_id"].startswith("align_")
    assert align["organization_id"] == org_id
    assert align["agent_id"] == "agent_outreach_1"
    assert align["aligned"] is True
    assert align["status"] == "agent_aligned_certified"
