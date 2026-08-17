"""Unit tests for Wave 7 Strategic Enhancements: Treasury Stress Tester, Compliance Binder, Strategy Route Optimizer, and Swarm Dispatcher."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    accounting_db,
    authority_integrity,
    business_metrics,
    compliance_deadlines,
    finance_db,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    accounting_db.ensure_schema(conn)
    authority_integrity.ensure_schema(conn)
    business_metrics.ensure_schema(conn)
    organization_db.ensure_schema(conn)


    org_id = organization_db.create_organization(
        conn,
        name="Wave7Corp",
        purpose="Wave 7 testing",
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
        purpose="Run wave 7 tests",
        responsibilities=["wave7"],
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

    obj = objectives_db.create_objective(
        conn,
        desired_outcome="Autonomous enterprise expansion",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_simulate_treasury_runway_stress_test(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    acc_id = finance_db.create_treasury_account(
        conn, organization_id=org_id, currency="USD", name="operating"
    )
    finance_db.record_entry(
        conn,
        account_id=acc_id,
        kind="deposit",
        amount_minor=10000,
        currency="USD",
        idempotency_key="dep_wave7_stress",
        evidence={"source": "capital"},
    )

    res = finance_db.simulate_treasury_runway_stress_test(
        conn, organization_id=org_id, stress_revenue_drop_pct=25
    )

    assert res["organization_id"] == org_id
    assert res["status"] in {"pass", "warning", "critical"}
    assert res["stressed_daily_burn_minor"] > 0


def test_synthesize_compliance_audit_binder(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    binder = compliance_deadlines.synthesize_compliance_audit_binder(conn, org_id)

    assert binder["binder_id"].startswith("binder_")
    assert binder["organization_id"] == org_id
    assert binder["status"] == "certified"
    assert len(binder["merkle_root"]) == 64


def test_optimize_cross_market_strategy_routes(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    res = business_metrics.optimize_cross_market_strategy_routes(conn, org_id)

    assert res["organization_id"] == org_id
    assert res["status"] == "optimized"


def test_dispatch_cross_functional_team_swarm(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    swarm = organization_db.dispatch_cross_functional_team_swarm(
        conn, organization_id=org_id, objective_id=obj_id, roles=["engineering", "finance"]
    )

    assert swarm["swarm_id"].startswith("swarm_")
    assert swarm["organization_id"] == org_id
    assert swarm["objective_id"] == obj_id
    assert swarm["team_size"] == 2
    assert swarm["status"] == "dispatched"
