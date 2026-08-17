"""Unit tests for Wave 10 Strategic Enhancements: Dynamic Pricing, Churn Risk Mining, Affiliate Commissions, and Content Release Dispatcher."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    company_email,
    journey,
    metered_billing,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    company_email.ensure_schema(conn)
    metered_billing.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    org_id = organization_db.create_organization(
        conn,
        name="Wave10Corp",
        purpose="Wave 10 testing",
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
        purpose="Run wave 10 tests",
        responsibilities=["wave10"],
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
        desired_outcome="Enterprise GTM & LTV Expansion",
        originator="employee:ceo",
        organization_id=org_id,
        max_spend_minor=10000,
        currency="USD",
    )
    objectives_db.transition_objective(conn, obj.id, "accepted", actor="employee:ceo")
    obj = objectives_db.transition_objective(conn, obj.id, "planned", actor="employee:ceo")

    return conn, org_id, obj.id


def test_evaluate_and_authorize_custom_pricing_tier(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    res = metered_billing.evaluate_and_authorize_custom_pricing_tier(
        conn,
        organization_id=org_id,
        customer_id="cust_enterprise_001",
        volume_tier="tier_enterprise",
        discount_pct=20,
        max_allowed_discount_pct=25,
    )

    assert res["authorized"] is True
    assert res["permit_id"].startswith("permit_price_")
    assert res["status"] == "authorized"


def test_process_referral_affiliate_commission_payouts(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    # Insert a customer ledger record
    meter_id = metered_billing.create_meter(
        conn, organization_id=org_id, name="api_tokens_w10", currency="USD", unit_price_microminor=1000, unit_name="tokens"
    )
    metered_billing.record_usage(
        conn, meter_id=meter_id, customer_id="cust_aff_ref", quantity=50, idempotency_key="ev_w10_1", evidence={"source": "api"}
    )

    metered_billing.run_automated_customer_billing(
        conn, organization_id=org_id, customer_id="cust_aff_ref"
    )

    payout = metered_billing.process_referral_affiliate_commission_payouts(
        conn,
        organization_id=org_id,
        affiliate_id="affiliate_partner_99",
        customer_id="cust_aff_ref",
        commission_pct=15,
    )

    assert payout["payout_id"].startswith("payout_aff_")
    assert payout["affiliate_id"] == "affiliate_partner_99"
    assert payout["status"] == "processed"



def test_mine_churn_risk_and_trigger_retention_offer(tmp_path):
    conn, org_id, _ = _setup_test_db(tmp_path)

    retention = journey.mine_churn_risk_and_trigger_retention_offer(
        conn, organization_id=org_id, customer_id="cust_declining_use", usage_drop_pct=40
    )

    assert retention["at_risk"] is True
    assert retention["retention_offer"]["discount_pct"] == 20
    assert retention["status"] == "retention_triggered"


def test_dispatch_marketing_content_release_with_proof(tmp_path):
    conn, org_id, obj_id = _setup_test_db(tmp_path)

    rel = company_email.dispatch_marketing_content_release_with_proof(
        conn,
        organization_id=org_id,
        objective_id=obj_id,
        channel="blog_announcement",
        content="Charterforge Business OS Wave 10 Release Notes",
    )

    assert rel["release_id"].startswith("mkt_rel_")
    assert rel["organization_id"] == org_id
    assert rel["channel"] == "blog_announcement"
    assert len(rel["content_sha256"]) == 64
    assert rel["status"] == "published"
