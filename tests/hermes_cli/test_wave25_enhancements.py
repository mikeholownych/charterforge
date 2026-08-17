"""Unit tests for Wave 25 Strategic Enhancements: Franchise Brand Licensing Engine, Contract Price Escalation Engine, Multi-Cloud Compute Cost Optimizer, and Swarm Token Budget Allocator."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_commitments,
    objectives_db,
    organization_db,
    resource_budget,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_commitments.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    resource_budget.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="FranchisorParentW25",
        purpose="Parent Wave 25 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    sub_id = organization_db.create_organization(
        conn,
        name="FranchiseeSubW25",
        purpose="Franchisee Wave 25 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, sub_id


def test_execute_franchise_brand_licensing_clearing(tmp_path):
    conn, parent_id, sub_id = _setup_test_db(tmp_path)

    royalty = organization_db.execute_franchise_brand_licensing_clearing(
        conn,
        organization_id=parent_id,
        franchisee_org_id=sub_id,
        gross_revenue_minor=2000000,
        royalty_pct=5.0,
    )

    assert royalty["franchise_clearing_id"].startswith("royalty_")
    assert royalty["franchisor_org_id"] == parent_id
    assert royalty["franchisee_org_id"] == sub_id
    assert royalty["royalty_fee_minor"] == 100000
    assert royalty["status"] == "royalty_fee_cleared"


def test_apply_contract_renewal_price_escalation(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    escala = business_commitments.apply_contract_renewal_price_escalation(
        conn,
        organization_id=parent_id,
        customer_id="cust_enterprise_1",
        current_contract_value_minor=1000000,
        escalation_pct=5.0,
    )

    assert escala["price_escalation_id"].startswith("escala_")
    assert escala["organization_id"] == parent_id
    assert escala["customer_id"] == "cust_enterprise_1"
    assert escala["new_contract_value_minor"] == 1050000
    assert escala["status"] == "contract_value_escalated"


def test_optimize_multicloud_compute_workload_routing(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    route = resource_budget.optimize_multicloud_compute_workload_routing(
        conn, organization_id=parent_id, workload_units=100
    )

    assert route["multicloud_route_id"].startswith("mcroute_")
    assert route["organization_id"] == parent_id
    assert route["selected_cloud_provider"] == "daytona"
    assert route["savings_pct_vs_standard"] > 40.0
    assert route["status"] == "workload_routed_optimal_spot"


def test_reallocate_agent_swarm_token_budgets(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    realloc = resource_budget.reallocate_agent_swarm_token_budgets(
        conn,
        organization_id=parent_id,
        donor_agent_id="agent_idle_3",
        recipient_agent_id="agent_outreach_1",
        token_amount=50000,
    )

    assert realloc["token_reallocation_id"].startswith("tokrealloc_")
    assert realloc["organization_id"] == parent_id
    assert realloc["donor_agent_id"] == "agent_idle_3"
    assert realloc["recipient_agent_id"] == "agent_outreach_1"
    assert realloc["tokens_reallocated"] == 50000
    assert realloc["status"] == "token_budget_reallocated"
