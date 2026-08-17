"""Unit tests for Wave 33 Strategic Enhancements: WebGL Ambient Shader Engine, Skeleton Shimmer Architecture, Interactive Animated SVG Data Viz, and Figma Token Sync Engine."""

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
        name="DesignLuxuryW33",
        purpose="Parent Wave 33 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_generate_webgl_ambient_shader_background(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    shader = journey.generate_webgl_ambient_shader_background(
        conn, organization_id=parent_id, shader_preset="aurora_glass_mesh"
    )

    assert shader["webgl_shader_id"].startswith("shader_")
    assert shader["organization_id"] == parent_id
    assert shader["shader_preset"] == "aurora_glass_mesh"
    assert shader["gpu_fps_cap"] == 60
    assert shader["status"] == "webgl_ambient_shader_generated"


def test_generate_skeleton_shimmer_loader_architecture(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    shim = business_metrics.generate_skeleton_shimmer_loader_architecture(
        conn, organization_id=parent_id, component_type="dashboard_grid"
    )

    assert shim["skeleton_shimmer_id"].startswith("skelshim_")
    assert shim["organization_id"] == parent_id
    assert shim["component_type"] == "dashboard_grid"
    assert shim["perceived_latency_reduction_pct"] == 40.0
    assert shim["status"] == "skeleton_shimmer_architecture_generated"


def test_generate_interactive_animated_svg_chart(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    chart = business_metrics.generate_interactive_animated_svg_chart(
        conn, organization_id=parent_id, chart_type="area_gradient_sparkline"
    )

    assert chart["interactive_svg_chart_id"].startswith("svgchart_")
    assert chart["organization_id"] == parent_id
    assert chart["chart_type"] == "area_gradient_sparkline"
    assert chart["interactive_tooltip_enabled"] is True
    assert chart["status"] == "interactive_svg_chart_generated"


def test_sync_figma_design_tokens_to_codebase(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    sync_res = security_audit.sync_figma_design_tokens_to_codebase(
        conn, organization_id=parent_id, figma_file_key="fig_2026_q3_ds"
    )

    assert sync_res["figma_token_sync_id"].startswith("figsync_")
    assert sync_res["organization_id"] == parent_id
    assert sync_res["figma_file_key"] == "fig_2026_q3_ds"
    assert sync_res["tokens_ingested_count"] >= 40
    assert sync_res["design_token_drift_detected"] is False
    assert sync_res["status"] == "figma_design_tokens_synced"
