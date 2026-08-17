"""Unit tests for Wave 12 Strategic Enhancements: Corporate Knowledge Graph, FX Hedging Engine, Self-Evolving Governance, and Vendor SLA Renewal Evaluator."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    finance_db,
    journey,
    objective_policy,
    objectives_db,
    organization_db,
    procurement_policy,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    procurement_policy.ensure_schema(conn)


    org_id = organization_db.create_organization(
        conn,
        name="Wave12Corp",
        purpose="Wave 12 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, org_id, "obj_w12"


def test_synthesize_corporate_knowledge_graph(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    graph = journey.synthesize_corporate_knowledge_graph(conn, organization_id=org_id)

    assert graph["graph_id"].startswith("graph_")
    assert graph["organization_id"] == org_id
    assert graph["node_count"] >= 2
    assert graph["status"] == "synthesized"


def test_hedge_foreign_exchange_exposure(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    acc_id = finance_db.create_treasury_account(
        conn, organization_id=org_id, currency="EUR", name="operating_eur"
    )
    finance_db.record_entry(
        conn,
        account_id=acc_id,
        kind="deposit",
        amount_minor=15000,
        currency="EUR",
        idempotency_key="dep_w12_eur",
        evidence={"source": "eu_revenue"},
    )

    hedge = finance_db.hedge_foreign_exchange_exposure(
        conn, organization_id=org_id, base_currency="USD"
    )

    assert hedge["hedge_id"].startswith("fx_")
    assert hedge["organization_id"] == org_id
    assert hedge["exposures_count"] == 1
    assert hedge["total_hedged_minor"] == 15000
    assert hedge["status"] == "hedged"


def test_evolve_corporate_governance_policies(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    pol = objective_policy.evolve_corporate_governance_policies(conn, organization_id=org_id)

    assert pol["policy_version"].startswith("pol_v")
    assert pol["organization_id"] == org_id
    assert pol["status"] == "evolved"


def test_evaluate_vendor_contract_renewal_terms(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    eval_res = procurement_policy.evaluate_vendor_contract_renewal_terms(
        conn,
        organization_id=org_id,
        vendor_id="vendor_aws_cloud",
        annual_cost_minor=50000,
        sla_compliance_pct=99.8,
    )

    assert eval_res["evaluation_id"].startswith("ren_")
    assert eval_res["organization_id"] == org_id
    assert eval_res["vendor_id"] == "vendor_aws_cloud"
    assert eval_res["renew_approved"] is True
    assert eval_res["status"] == "authorized_renewal"
