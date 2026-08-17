"""Unit tests for autonomous strategy A/B experiment evaluation and route switching."""

from __future__ import annotations

import sqlite3
import time

from hermes_cli import business_metrics, objectives_db, organization_db


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_metrics.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="StrategyCorp",
        purpose="A/B strategy testing",
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
        purpose="Run strategy tests",
        responsibilities=["strategy"],
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
        desired_outcome="Optimize conversion funnel",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_evaluate_and_switch_strategy_routes_accepts_supported_experiment(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)
    now = int(time.time())

    metric_id, _ = business_metrics.register_metric(
        conn,
        organization_id=org_id,
        metric_key="checkout_conversion_rate",
        name="Checkout Conversion",
        unit="ratio",
        preferred_direction="increase",
        source_system="analytics",
        verifier="control:verification",
        idempotency_key="metric_checkout_conv_001",
        created_by="employee:ceo",
    )

    exp_id, _ = business_metrics.start_experiment(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        name="Streamlined 1-Step Checkout",
        hypothesis="Reducing checkout steps increases conversion by > 20%",
        metric_id=metric_id,
        comparator="gte",
        success_threshold_scaled=200000,  # 20.00%
        starts_at=now - 3600,
        ends_at=now + 3600,  # Active during creation
        max_spend_minor=1000,
        currency="USD",
        idempotency_key="exp_streamlined_checkout_001",
        created_by="employee:ceo",
    )

    # Record observation exceeding success threshold (25% = 250000 scaled)
    business_metrics.record_observation(
        conn,
        organization_id=org_id,
        metric_id=metric_id,
        value_scaled=250000,
        observed_at=now,
        source_reference="analytics:checkout:1001",
        verifier="control:verification",
        evidence={"observed_conversion": 0.25},
    )

    # Review due experiments at now + 4000 (after ends_at)
    review_time = now + 4000
    business_metrics.dispatch_reviews(
        conn, organization_id=org_id, now=review_time
    )

    summary = business_metrics.evaluate_and_switch_strategy_routes(
        conn, organization_id=org_id
    )

    assert exp_id in summary["accepted"]

    row = conn.execute(
        "SELECT status, reason FROM strategy_experiment_state WHERE experiment_id=?",
        (exp_id,),
    ).fetchone()
    assert row["status"] == "accepted"
    assert "supported by empirical metric evidence" in row["reason"]
