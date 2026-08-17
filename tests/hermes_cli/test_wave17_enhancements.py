"""Unit tests for Wave 17 Strategic Enhancements: Skill Retraining Dispatcher, Inter-Company IP Royalty Engine, Customer Health Indexer, and Treasury Tax Routing Optimizer."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    accounting_db,
    finance_db,
    hiring_policy,
    journey,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    accounting_db.ensure_schema(conn)
    finance_db.ensure_schema(conn)
    hiring_policy.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="ParentCorpW17",
        purpose="Parent Wave 17 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    sub_id = organization_db.create_organization(
        conn,
        name="SubCorpW17",
        purpose="Sub Wave 17 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, sub_id


def test_dispatch_employee_skill_retraining_program(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    retrain = hiring_policy.dispatch_employee_skill_retraining_program(
        conn,
        organization_id=parent_id,
        employee_id="emp_eng_1",
        target_capability="security_auditing",
    )

    assert retrain["program_id"].startswith("retrain_")
    assert retrain["organization_id"] == parent_id
    assert retrain["employee_id"] == "emp_eng_1"
    assert retrain["target_capability"] == "security_auditing"
    assert retrain["status"] == "retraining_dispatched"


def test_calculate_and_settle_intercompany_ip_royalties(tmp_path):
    conn, parent_id, sub_id = _setup_test_db(tmp_path)

    roy = accounting_db.calculate_and_settle_intercompany_ip_royalties(
        conn,
        parent_org_id=parent_id,
        child_org_id=sub_id,
        net_revenue_minor=200000,
        royalty_pct=5.0,
    )

    assert roy["royalty_id"].startswith("roy_")
    assert roy["parent_org_id"] == parent_id
    assert roy["child_org_id"] == sub_id
    assert roy["royalty_fee_minor"] == 10000
    assert roy["status"] == "royalty_settled"


def test_predict_customer_health_and_nps_velocity(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    health = journey.predict_customer_health_and_nps_velocity(
        conn, organization_id=parent_id, customer_id="cust_acme_corp"
    )

    assert health["index_id"].startswith("health_")
    assert health["organization_id"] == parent_id
    assert health["customer_id"] == "cust_acme_corp"
    assert health["health_score"] > 80.0
    assert health["status"] == "healthy_expansion_candidate"


def test_optimize_cross_border_treasury_tax_routing(tmp_path):
    conn, parent_id, sub_id = _setup_test_db(tmp_path)

    tax_route = finance_db.optimize_cross_border_treasury_tax_routing(
        conn,
        organization_id=parent_id,
        source_org_id=parent_id,
        destination_org_id=sub_id,
        amount_minor=100000,
    )

    assert tax_route["route_id"].startswith("taxroute_")
    assert tax_route["organization_id"] == parent_id
    assert tax_route["source_org_id"] == parent_id
    assert tax_route["destination_org_id"] == sub_id
    assert tax_route["status"] == "tax_route_optimized"
