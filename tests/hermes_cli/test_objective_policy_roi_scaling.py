"""Unit tests for closed-loop ROI budget scaling in objective_policy."""

from __future__ import annotations

import sqlite3
import time
from typing import Any

import pytest

from hermes_cli import (
    accounting_db,
    finance_db,
    objective_policy,
    objectives_db,
    organization_db,
    outcome_attribution,
    payments,
)


def _setup_test_db(tmp_path) -> sqlite3.Connection:
    conn = objectives_db.connect(tmp_path / "authority.db")
    finance_db.ensure_schema(conn)
    accounting_db.ensure_schema(conn)
    organization_db.ensure_schema(conn)
    outcome_attribution.ensure_schema(conn)
    payments.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="TestOrg",
        purpose="Test Purpose",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    ceo_id = organization_db.propose_employee(
        conn,
        organization_id=org_id,
        display_name="Charterforge CEO",
        title="Chief Executive Officer",
        level="ceo",
        manager_id=None,
        proposed_by="setup:user",
    )
    organization_db.transition_employee(conn, ceo_id, "approved", actor="setup:user")
    organization_db.transition_employee(conn, ceo_id, "provisioning", actor="setup:user")
    organization_db.create_mandate(
        conn,
        ceo_id,
        purpose="Run the company inside its charter",
        responsibilities=["portfolio management"],
        decision_rights=["hire within budget"],
        prohibited_actions=["expand own charter"],
        capabilities=["objectives.manage"],
        systems=["objectives"],
        kpis=["runway", "revenue"],
        escalation={"to": "operator", "when": "outside charter"},
        toolsets=["cli"],
        skills=[],
        budget_minor=100000,
        expires_at=None,
        created_by="setup:user",
    )
    organization_db.transition_employee(conn, ceo_id, "active", actor="setup:user", profile_name="ceo")

    finance_db.create_treasury_account(conn, organization_id=org_id, currency="USD")
    account_id = finance_db.operating_account_for_organization(conn, org_id, "USD")
    finance_db.seed_initial_capital(
        conn, account_id=account_id, amount_minor=100000, currency="USD", actor="test"
    )
    return conn


def _charter() -> dict[str, Any]:
    return {
        "enabled": True,
        "operating_mode": "autonomous",
        "max_autonomous_risk": "high",
        "permit_ttl_seconds": 300,
        "max_action_spend_minor": 5000,
        "allowed_capabilities": ["payments.execute", "test.capability"],
        "allowed_systems": ["test_system"],
        "solo_founder": {"toolsets": ["cli"], "skills": []},
    }


def _create_planned_objective_and_action(
    conn: sqlite3.Connection, org_id: str, max_spend_minor: int, estimated_cost_minor: int
) -> tuple[Any, str]:
    obj = objectives_db.create_objective(
        conn,
        desired_outcome="Test Objective",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=max_spend_minor,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    plan_id = objectives_db.create_plan(
        conn,
        obj.id,
        assumptions=[],
        tasks=[{"id": "t1"}],
        dependencies=[],
        risks=[],
        created_by="employee:ceo",
    )

    action_id = objectives_db.propose_action(
        conn,
        objective_id=obj.id,
        plan_id=plan_id,
        action_type="test_action",
        payload={
            "system": "test_system",
            "target_resource": "res_1",
            "idempotency_key": "123456789012345678",
        },
        expected_outcome="outcome",
        required_capability="test.capability",
        verification_method="deterministic_check",
        risk_class="low",
        reversible=True,
        estimated_cost_minor=estimated_cost_minor,
        proposed_by="employee:ceo",
    )
    return obj, action_id


def test_unverified_or_zero_yield_does_not_scale_budget(tmp_path):
    conn = _setup_test_db(tmp_path)
    org_id = organization_db.active_ceo(conn)["organization_id"]

    # Objective baseline max spend = 1000 minor ($10.00). Cost = 1100 minor ($11.00).
    obj, action_id = _create_planned_objective_and_action(
        conn, org_id, max_spend_minor=1000, estimated_cost_minor=1100
    )

    decision, permit_id = objective_policy.evaluate_and_record(
        conn,
        action_id=action_id,
        charter=_charter(),
        executor="employee:ceo",
        policy_version="v1",
    )

    assert decision.verdict == "escalate"
    assert "exceeds the objective budget" in decision.reason
    assert permit_id is None


def test_verified_positive_net_yield_scales_effective_budget(tmp_path):
    conn = _setup_test_db(tmp_path)
    org_id = organization_db.active_ceo(conn)["organization_id"]

    obj, action_id = _create_planned_objective_and_action(
        conn, org_id, max_spend_minor=1000, estimated_cost_minor=1150
    )

    now = int(time.time())
    conn.execute(
        """INSERT INTO payment_intents (
             id,organization_id,account_id,objective_id,direction,provider,
             party_json,amount_minor,currency,purpose,status,provider_reference,
             idempotency_key,metadata_json,tax_minor,created_at,updated_at
           ) VALUES (
             'payment_test_1',?, 'treasury_1',?,'incoming','fake','{}',2200,'USD',
             'sale','succeeded','provider_1','payment-key-00000001','{}',200,?,?
           )""",
        (org_id, obj.id, now, now),
    )
    conn.execute(
        """INSERT INTO payment_provider_readbacks (
             id,payment_intent_id,provider,provider_reference,status,
             amount_minor,currency,evidence_json,observed_at
           ) VALUES ('readback_1','payment_test_1','fake','provider_1','succeeded',2200,'USD','{}',?)""",
        (now,),
    )
    outcome_attribution.sync_authoritative_links(conn, org_id)

    # Action cost is 1150 minor ($11.50). Baseline is 1000.
    # Net yield = 2200 - 200 tax = 2000 minor.
    # Scaled budget = 1000 + min(2000, 1000 * 0.25) = 1250 ($12.50).
    decision, permit_id = objective_policy.evaluate_and_record(
        conn,
        action_id=action_id,
        charter=_charter(),
        executor="employee:ceo",
        policy_version="v1",
    )

    assert decision.verdict == "permit", f"Reason: {decision.reason}"
    assert permit_id is not None


def test_contradicted_attribution_ignored_for_scaling(tmp_path):
    conn = _setup_test_db(tmp_path)
    org_id = organization_db.active_ceo(conn)["organization_id"]

    obj, action_id = _create_planned_objective_and_action(
        conn, org_id, max_spend_minor=1000, estimated_cost_minor=1150
    )

    now = int(time.time())
    conn.execute(
        """INSERT INTO payment_intents (
             id,organization_id,account_id,objective_id,direction,provider,
             party_json,amount_minor,currency,purpose,status,provider_reference,
             idempotency_key,metadata_json,tax_minor,created_at,updated_at
           ) VALUES (
             'payment_test_2',?, 'treasury_1',?,'incoming','fake','{}',2200,'USD',
             'sale','succeeded','provider_2','payment-key-00000002','{}',200,?,?
           )""",
        (org_id, obj.id, now, now),
    )
    conn.execute(
        """INSERT INTO payment_provider_readbacks (
             id,payment_intent_id,provider,provider_reference,status,
             amount_minor,currency,evidence_json,observed_at
           ) VALUES ('readback_2','payment_test_2','fake','provider_2','succeeded',2200,'USD','{}',?)""",
        (now,),
    )
    outcome_attribution.sync_authoritative_links(conn, org_id)

    # Record contradiction (chargeback/refund)
    conn.execute(
        """INSERT INTO payment_provider_readbacks (
             id,payment_intent_id,provider,provider_reference,status,
             amount_minor,currency,evidence_json,observed_at
           ) VALUES ('readback_reversed','payment_test_2','fake','provider_2','reversed',2200,'USD','{"reversal":"confirmed"}',?)""",
        (now + 10,),
    )
    outcome_attribution.sync_authoritative_links(conn, org_id)

    decision, permit_id = objective_policy.evaluate_and_record(
        conn,
        action_id=action_id,
        charter=_charter(),
        executor="employee:ceo",
        policy_version="v1",
    )

    # Scaled budget bonus is 0 due to contradiction, so cost 1150 > baseline 1000 escalates
    assert decision.verdict == "escalate"
    assert permit_id is None
