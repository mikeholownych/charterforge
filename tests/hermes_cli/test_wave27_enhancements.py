"""Unit tests for Wave 27 Strategic Enhancements: Real-Time Capital Re-Balancing Autopilot, Competitive Counter-Strategy Dispatcher, Board Resolution Auto-Execution Engine, and Cross-Departmental Dependency Resolver."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_metrics,
    finance_db,
    objectives_db,
    operational_control,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_metrics.ensure_schema(conn)
    finance_db.ensure_schema(conn)
    operational_control.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="MasterCorpW27",
        purpose="Parent Wave 27 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_auto_rebalance_departmental_capital_allocation(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    rebal = finance_db.auto_rebalance_departmental_capital_allocation(
        conn, organization_id=parent_id
    )

    assert rebal["capital_rebalance_id"].startswith("caprebal_")
    assert rebal["organization_id"] == parent_id
    assert rebal["capital_reallocated_minor"] > 0
    assert rebal["efficiency_gain_pct"] > 30.0
    assert rebal["status"] == "capital_rebalanced_optimal"


def test_dispatch_competitive_counter_strategy(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    counter = business_metrics.dispatch_competitive_counter_strategy(
        conn,
        organization_id=parent_id,
        competitor_name="RivalSaaS",
        signal_type="price_cut",
    )

    assert counter["counter_strategy_id"].startswith("counter_")
    assert counter["organization_id"] == parent_id
    assert counter["competitor_name"] == "RivalSaaS"
    assert counter["activated_strategy_route"] == "defensive_value_bundling"
    assert counter["status"] == "counter_strategy_dispatched"


def test_auto_execute_approved_board_resolutions(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    board_exec = organization_db.auto_execute_approved_board_resolutions(
        conn, organization_id=parent_id, resolution_id="res_2026_q3_01"
    )

    assert board_exec["board_execution_id"].startswith("boardexec_")
    assert board_exec["organization_id"] == parent_id
    assert board_exec["resolution_id"] == "res_2026_q3_01"
    assert board_exec["mandates_provisioned_count"] == 3
    assert board_exec["status"] == "board_resolution_executed"


def test_resolve_cross_departmental_objective_dependencies(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    dep = operational_control.resolve_cross_departmental_objective_dependencies(
        conn, organization_id=parent_id
    )

    assert dep["dependency_resolution_id"].startswith("depres_")
    assert dep["organization_id"] == parent_id
    assert dep["dependencies_scanned_count"] >= 5
    assert dep["critical_path_accelerated"] is True
    assert dep["status"] == "dependencies_resolved_unblocked"
