"""Unit tests for Wave 26 Strategic Enhancements: Strategic Goal Cascade Engine, Enterprise Symphony Orchestrator, Goal Deviation Radar, and Enterprise Valuation Maximizer."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    finance_db,
    journey,
    objective_policy,
    objectives_db,
    organization_db,
    security_audit,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="MasterCorpW26",
        purpose="Parent Wave 26 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_cascade_strategic_goal_alignment(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    cascade = objective_policy.cascade_strategic_goal_alignment(
        conn,
        organization_id=parent_id,
        macro_goal_name="reach_50m_arr",
        target_revenue_minor=5000000000,
    )

    assert cascade["strategic_cascade_id"].startswith("cascade_")
    assert cascade["organization_id"] == parent_id
    assert cascade["sub_objectives_cascaded_count"] == 3
    assert cascade["status"] == "goal_cascaded_aligned"


def test_orchestrate_enterprise_symphony_loop(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    symphony = journey.orchestrate_enterprise_symphony_loop(
        conn, organization_id=parent_id
    )

    assert symphony["enterprise_symphony_id"].startswith("symphony_")
    assert symphony["organization_id"] == parent_id
    assert symphony["subsystems_orchestrated_count"] >= 5
    assert symphony["health_score"] == 100.0
    assert symphony["status"] == "symphony_loop_executed_aligned"


def test_scan_strategic_goal_deviation_radar(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    radar = security_audit.scan_strategic_goal_deviation_radar(
        conn, organization_id=parent_id
    )

    assert radar["strategic_radar_id"].startswith("radar_")
    assert radar["organization_id"] == parent_id
    assert radar["metrics_monitored_count"] >= 10
    assert radar["alignment_confidence_pct"] > 90.0
    assert radar["status"] == "goals_on_track_aligned"


def test_calculate_and_maximize_enterprise_valuation(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    val = finance_db.calculate_and_maximize_enterprise_valuation(
        conn, organization_id=parent_id, arr_multiple=10.0
    )

    assert val["enterprise_valuation_id"].startswith("val_")
    assert val["organization_id"] == parent_id
    assert val["enterprise_valuation_minor"] == 5000000000
    assert val["rule_of_40_score"] == 55.0
    assert val["status"] == "valuation_maximized"
