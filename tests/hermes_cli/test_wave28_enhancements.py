"""Unit tests for Wave 28 Strategic Enhancements: Programmatic SEO Generator, Funnel Friction Miner & CRO Engine, Viral Referral & Social Proof Booster, and Interactive ROI Lead Magnet Engine."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_metrics,
    company_email,
    journey,
    objectives_db,
    organization_db,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_metrics.ensure_schema(conn)
    company_email.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="GrowthCorpW28",
        purpose="Parent Wave 28 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_generate_programmatic_seo_landing_matrix(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    seo = journey.generate_programmatic_seo_landing_matrix(
        conn, organization_id=parent_id
    )

    assert seo["seo_matrix_id"].startswith("seo_")
    assert seo["organization_id"] == parent_id
    assert seo["keywords_indexed_count"] >= 3
    assert seo["pages_generated_count"] >= 15
    assert seo["status"] == "seo_pages_indexed"


def test_mine_funnel_friction_and_optimize_conversion(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    cro = business_metrics.mine_funnel_friction_and_optimize_conversion(
        conn, organization_id=parent_id, funnel_stage="checkout"
    )

    assert cro["funnel_cro_id"].startswith("cro_")
    assert cro["organization_id"] == parent_id
    assert cro["funnel_stage"] == "checkout"
    assert cro["projected_conversion_lift_pct"] > 25.0
    assert cro["status"] == "funnel_friction_optimized"


def test_trigger_viral_social_proof_referral(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    viral = journey.trigger_viral_social_proof_referral(
        conn, organization_id=parent_id, customer_id="cust_enterprise_1"
    )

    assert viral["viral_referral_id"].startswith("viral_")
    assert viral["organization_id"] == parent_id
    assert viral["customer_id"] == "cust_enterprise_1"
    assert "achievement" in viral["milestone_badge"]

    assert viral["status"] == "viral_social_proof_issued"


def test_generate_interactive_roi_lead_magnet(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    lead = company_email.generate_interactive_roi_lead_magnet(
        conn,
        organization_id=parent_id,
        prospect_email="lead@enterprise.com",
        company_size=250,
    )

    assert lead["roi_lead_magnet_id"].startswith("roilead_")
    assert lead["organization_id"] == parent_id
    assert lead["prospect_email"] == "lead@enterprise.com"
    assert lead["projected_annual_savings_minor"] > 0
    assert lead["proposal_dispatched"] is True
    assert lead["status"] == "roi_proposal_dispatched"
