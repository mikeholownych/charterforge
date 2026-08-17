"""Unit tests for Wave 29 Strategic Enhancements: Competitor Comparison SEO Generator, Predictive Intent Lead Nurturer, Interactive Maturity Benchmark Test, and Omnichannel Social Proof Syndicator."""

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
        name="HighGrowthW29",
        purpose="Parent Wave 29 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_generate_competitor_comparison_seo_matrix(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    comp_seo = journey.generate_competitor_comparison_seo_matrix(
        conn, organization_id=parent_id
    )

    assert comp_seo["competitor_seo_id"].startswith("compseo_")
    assert comp_seo["organization_id"] == parent_id
    assert comp_seo["competitors_compared_count"] >= 3
    assert comp_seo["comparison_pages_indexed_count"] >= 9
    assert comp_seo["status"] == "competitor_seo_matrix_indexed"


def test_nurture_high_intent_visitor_behavior(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    nurture = company_email.nurture_high_intent_visitor_behavior(
        conn, organization_id=parent_id, visitor_email="prospect@enterprise.com"
    )

    assert nurture["intent_nurture_id"].startswith("nurture_")
    assert nurture["organization_id"] == parent_id
    assert nurture["visitor_email"] == "prospect@enterprise.com"
    assert nurture["intent_score"] > 80.0
    assert nurture["status"] == "intent_nurture_dispatched"


def test_run_interactive_maturity_benchmark_test(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    bench = business_metrics.run_interactive_maturity_benchmark_test(
        conn, organization_id=parent_id, prospect_email="lead@co.com", industry="fintech"
    )

    assert bench["benchmark_test_id"].startswith("bench_")
    assert bench["organization_id"] == parent_id
    assert bench["prospect_email"] == "lead@co.com"
    assert bench["industry"] == "fintech"
    assert bench["governance_maturity_score"] > 50.0
    assert bench["status"] == "benchmark_assessment_delivered"


def test_syndicate_verified_case_study_social_proof(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    syndicate = company_email.syndicate_verified_case_study_social_proof(
        conn, organization_id=parent_id, case_study_id="case_fintech_01"
    )

    assert syndicate["case_study_syndication_id"].startswith("syndication_")
    assert syndicate["organization_id"] == parent_id
    assert syndicate["case_study_id"] == "case_fintech_01"
    assert syndicate["channels_syndicated_count"] >= 3
    assert syndicate["status"] == "case_study_social_proof_syndicated"
