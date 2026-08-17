"""Unit tests for Wave 30 Strategic Enhancements: Generative AI Search Engine Optimizer (GEO/AISO), Micro-Interactive Growth Tool Matrix, Dynamic Persona-Based Personalizer, and Exit-Intent Funnel Recovery Engine."""

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
        name="AIGrowthCorpW30",
        purpose="Parent Wave 30 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_generate_generative_ai_search_optimization_matrix(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    geo = journey.generate_generative_ai_search_optimization_matrix(
        conn, organization_id=parent_id
    )

    assert geo["generative_ai_seo_id"].startswith("geo_")
    assert geo["organization_id"] == parent_id
    assert geo["topics_indexed_count"] >= 3
    assert geo["rag_fact_triples_generated_count"] >= 60
    assert geo["citation_authority_score"] > 90.0
    assert geo["status"] == "generative_ai_search_optimized"


def test_generate_micro_interactive_growth_tool_matrix(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    micro = business_metrics.generate_micro_interactive_growth_tool_matrix(
        conn, organization_id=parent_id
    )

    assert micro["micro_tool_matrix_id"].startswith("microtool_")
    assert micro["organization_id"] == parent_id
    assert micro["tools_deployed_count"] >= 3
    assert micro["backlink_domain_authority_lift"] > 10.0
    assert micro["status"] == "micro_growth_tools_deployed"


def test_personalize_landing_experience_for_persona(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    pers = business_metrics.personalize_landing_experience_for_persona(
        conn, organization_id=parent_id, visitor_persona="fintech_cto"
    )

    assert pers["persona_personalization_id"].startswith("personalization_")
    assert pers["organization_id"] == parent_id
    assert pers["visitor_persona"] == "fintech_cto"
    assert pers["projected_cro_lift_pct"] > 30.0
    assert pers["status"] == "landing_page_personalized"


def test_trigger_exit_intent_abandoned_funnel_recovery(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    exit_rec = company_email.trigger_exit_intent_abandoned_funnel_recovery(
        conn,
        organization_id=parent_id,
        prospect_email="abandoner@enterprise.com",
        abandoned_stage="pricing",
    )

    assert exit_rec["exit_intent_recovery_id"].startswith("exitrec_")
    assert exit_rec["organization_id"] == parent_id
    assert exit_rec["prospect_email"] == "abandoner@enterprise.com"
    assert exit_rec["abandoned_stage"] == "pricing"
    assert exit_rec["recovery_permit_issued"] is True
    assert exit_rec["status"] == "exit_intent_recovery_dispatched"
