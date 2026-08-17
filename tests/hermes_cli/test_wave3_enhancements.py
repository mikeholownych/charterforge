"""Unit tests for Wave 3 Strategic Enhancements: Treasury Allocator, Merkle Integrity Prober, Emergency Escalations, and Authority Bridge."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    authority_bridge,
    authority_integrity,
    finance_db,
    objectives_db,
    operational_control,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    authority_integrity.ensure_schema(conn)
    operational_control.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave3Corp",
        purpose="Wave 3 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    return conn, org_id


def test_treasury_reinvestment_evaluator(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    acc_id = finance_db.create_treasury_account(
        conn, organization_id=org_id, currency="USD", name="operating"
    )
    # Deposit $100.00 (10,000 minor)
    finance_db.record_entry(
        conn,
        account_id=acc_id,
        kind="deposit",
        amount_minor=10000,
        currency="USD",
        idempotency_key="dep_wave3_init",
        evidence={"source": "capital_injection"},
    )

    result = finance_db.evaluate_treasury_reinvestment_and_reserves(
        conn, organization_id=org_id, target_runway_days=30, daily_burn_minor=100
    )

    assert result["liquid_balance_minor"] == 10000
    assert result["target_reserve_minor"] == 3000
    assert result["surplus_reinvestment_capacity_minor"] == 7000
    assert result["reinvestment_recommended"] is True


def test_merkle_authority_chain_probe(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    probe = authority_integrity.probe_authority_chain_integrity(conn, org_id)

    assert probe["organization_id"] == org_id
    assert probe["status"] == "valid"
    assert len(probe["merkle_root"]) == 64
    assert "hiring_decisions" in probe["table_digests"]


def test_escalate_unhandled_interventions(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    iid = operational_control.raise_intervention(
        conn,
        organization_id=org_id,
        category="test_escalation",
        summary="Test intervention escalation",
        context={"test": True},
        options=[{"id": "opt1", "label": "Option 1"}],
    )

    escalated = operational_control.escalate_unhandled_interventions(
        conn, organization_id=org_id, max_unhandled_seconds=0
    )

    assert iid in escalated


def test_issue_scoped_delegation_bridge(tmp_path):
    conn, org_id = _setup_test_db(tmp_path)

    token = authority_bridge.issue_scoped_delegation_bridge(
        conn,
        parent_org_id=org_id,
        child_profile_name="worker_alpha",
        scoped_capabilities=["payments.execute"],
        max_spend_minor=5000,
    )

    assert token["bridge_id"].startswith("bridge_")
    assert token["parent_org_id"] == org_id
    assert token["child_profile_name"] == "worker_alpha"
    assert len(token["signature"]) == 64
    assert token["status"] == "active"
