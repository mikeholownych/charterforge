"""Unit tests for Wave 9 Strategic Enhancements: ICP Lead Scoring & Outreach, Support SLA Escalation, Marketing Campaign Attribution, and Customer Onboarding Playbook."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_metrics,
    company_email,
    journey,
    objectives_db,
    operational_control,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    company_email.ensure_schema(conn)
    operational_control.ensure_schema(conn)
    business_metrics.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave9Corp",
        purpose="Wave 9 testing",
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
        purpose="Run wave 9 tests",
        responsibilities=["wave9"],
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
        desired_outcome="GTM expansion and customer acquisition",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_score_and_dispatch_icp_outreach(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    res = company_email.score_and_dispatch_icp_outreach(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        lead_profile={
            "company_name": "Acme Inc",
            "email": "sales@acme.com",
            "headcount": 25,
            "budget_minor": 100000,
        },
    )

    assert res["qualified"] is True
    assert res["icp_score"] == 100
    assert res["dispatched"] is True
    assert res["email_receipt"]["status"] == "sent"


def test_dispatch_support_ticket_sla_escalation(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    res = operational_control.dispatch_support_ticket_sla_escalation(
        conn, organization_id=org_id, ticket_id="tkt_wave9_101", age_seconds=5000, max_sla_seconds=1800
    )

    assert res["ticket_id"] == "tkt_wave9_101"
    assert res["is_breached"] is True
    assert res["status"] == "escalated"
    assert res["intervention_id"].startswith("intervention_")



def test_attribute_marketing_campaign_conversion_yield(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    res = business_metrics.attribute_marketing_campaign_conversion_yield(
        conn, organization_id=org_id, campaign_id="cmp_google_gtm", campaign_spend_minor=5000
    )

    assert res["campaign_id"] == "cmp_google_gtm"
    assert res["organization_id"] == org_id
    assert res["campaign_spend_minor"] == 5000


def test_execute_customer_onboarding_playbook(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    res = journey.execute_customer_onboarding_playbook(
        conn, organization_id=org_id, customer_id="cust_wave9_buyer"
    )

    assert res["execution_id"].startswith("onboard_")
    assert res["organization_id"] == org_id
    assert res["customer_id"] == "cust_wave9_buyer"
    assert res["steps_completed"] == 4
    assert res["status"] == "active"
