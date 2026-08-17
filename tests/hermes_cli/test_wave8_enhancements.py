"""Unit tests for Wave 8 Strategic Enhancements: Inter-Company Clearing, Mandate Federation, Autonomy Governor, and Corporate IP Packager."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    finance_db,
    journey,
    objectives_db,
    operational_control,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    operational_control.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="ParentCorp",
        purpose="Parent Wave 8 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    child_id = organization_db.create_organization(
        conn,
        name="ChildSubCorp",
        purpose="Child Wave 8 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, child_id


def test_settle_intercompany_treasury_clearing(tmp_path):
    conn, p_id, c_id = _setup_test_db(tmp_path)

    settlement = finance_db.settle_intercompany_treasury_clearing(
        conn, parent_org_id=p_id, child_org_id=c_id, amount_minor=5000
    )

    assert settlement["settlement_id"].startswith("clear_")
    assert settlement["parent_org_id"] == p_id
    assert settlement["child_org_id"] == c_id
    assert settlement["amount_minor"] == 5000
    assert settlement["status"] == "settled"


def test_federate_cross_entity_mandate(tmp_path):
    conn, p_id, c_id = _setup_test_db(tmp_path)

    fed = organization_db.federate_cross_entity_mandate(
        conn,
        parent_org_id=p_id,
        child_org_id=c_id,
        employee_id="ceo_p",
        capabilities=["objectives.manage"],
        max_spend_minor=15000,
    )

    assert fed["federation_id"].startswith("fed_")
    assert fed["parent_org_id"] == p_id
    assert fed["child_org_id"] == c_id
    assert fed["status"] == "federated"
    assert fed["bridge_token"]["bridge_id"].startswith("bridge_")


def test_evaluate_and_recover_autonomy_mode(tmp_path):
    conn, p_id, _ = _setup_test_db(tmp_path)

    operational_control.set_autonomy_mode(
        conn, mode="paused", actor="test:actor", reason="Temporary test pause"
    )

    res = operational_control.evaluate_and_recover_autonomy_mode(
        conn, organization_id=p_id
    )

    assert res["organization_id"] == p_id
    assert res["mode"] == "autonomous"
    assert res["recovered"] is True


def test_package_corporate_ip_bundle(tmp_path):
    conn, p_id, _ = _setup_test_db(tmp_path)

    bundle = journey.package_corporate_ip_bundle(
        conn, organization_id=p_id, sop_ids=["sop_onboarding_001"]
    )

    assert bundle["bundle_id"].startswith("ip_bundle_")
    assert bundle["organization_id"] == p_id
    assert bundle["sop_ids"] == ["sop_onboarding_001"]
    assert len(bundle["signature"]) == 64
    assert bundle["status"] == "packaged"
