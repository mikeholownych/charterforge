"""Unit tests for Wave 31 Strategic Enhancements: Design System Token Synthesizer, AI Graphic Asset Generator, UI Motion Architecture Generator, and Visual Hierarchy Health Inspector."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    business_metrics,
    company_email,
    journey,
    objectives_db,
    organization_db,
    security_audit,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    business_metrics.ensure_schema(conn)
    company_email.ensure_schema(conn)
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="DesignCorpW31",
        purpose="Parent Wave 31 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_synthesize_design_system_theme_tokens(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    tokens = journey.synthesize_design_system_theme_tokens(
        conn, organization_id=parent_id, theme_mode="dark_glassmorphic"
    )

    assert tokens["design_system_theme_id"].startswith("ds_tokens_")
    assert tokens["organization_id"] == parent_id
    assert tokens["theme_mode"] == "dark_glassmorphic"
    assert tokens["color_tokens_generated_count"] >= 20
    assert tokens["wcag_compliance_level"] == "AAA"
    assert tokens["status"] == "design_system_tokens_synthesized"


def test_generate_branded_visual_asset_pack(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    vpack = company_email.generate_branded_visual_asset_pack(
        conn, organization_id=parent_id, asset_category="hero_banner"
    )

    assert vpack["visual_asset_pack_id"].startswith("vpack_")
    assert vpack["organization_id"] == parent_id
    assert vpack["asset_category"] == "hero_banner"
    assert vpack["asset_prompts_generated_count"] >= 4
    assert vpack["status"] == "branded_visual_assets_generated"


def test_generate_ui_motion_architecture_manifest(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    motion = business_metrics.generate_ui_motion_architecture_manifest(
        conn, organization_id=parent_id, transition_preset="fluid_spring"
    )

    assert motion["ui_motion_architecture_id"].startswith("uimotion_")
    assert motion["organization_id"] == parent_id
    assert motion["transition_preset"] == "fluid_spring"
    assert motion["keyframes_defined_count"] >= 5
    assert motion["status"] == "ui_motion_architecture_generated"


def test_audit_visual_design_hierarchy_health(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    audit = security_audit.audit_visual_design_hierarchy_health(
        conn, organization_id=parent_id, target_component="landing_hero"
    )

    assert audit["visual_design_audit_id"].startswith("designaudit_")
    assert audit["organization_id"] == parent_id
    assert audit["target_component"] == "landing_hero"
    assert audit["visual_hierarchy_balance_score"] > 90.0
    assert audit["contrast_pass_rate_pct"] == 100.0
    assert audit["status"] == "visual_design_audit_passed"
