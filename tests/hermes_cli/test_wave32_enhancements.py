"""Unit tests for Wave 32 Strategic Enhancements: Dynamic Theme Auto-Switcher, Adaptive Breakpoint Engine, Fluid Typography Clamp Scaler, and Accessible Focus Ring & ARIA Architecture."""

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
        name="DesignPerfectW32",
        purpose="Parent Wave 32 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )

    return conn, parent_id


def test_adapt_dynamic_theme_mode(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    adapt = journey.adapt_dynamic_theme_mode(
        conn, organization_id=parent_id, client_pref="system_ambient"
    )

    assert adapt["theme_adaptation_id"].startswith("theme_adapt_")
    assert adapt["organization_id"] == parent_id
    assert adapt["client_preference"] == "system_ambient"
    assert adapt["anti_fouc_script_injected"] is True
    assert adapt["status"] == "dynamic_theme_mode_adapted"


def test_generate_adaptive_layout_breakpoint_matrix(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    break_mat = business_metrics.generate_adaptive_layout_breakpoint_matrix(
        conn, organization_id=parent_id
    )

    assert break_mat["layout_breakpoint_matrix_id"].startswith("break_")
    assert break_mat["organization_id"] == parent_id
    assert break_mat["breakpoints_configured_count"] >= 4
    assert break_mat["container_query_support"] is True
    assert break_mat["status"] == "adaptive_layout_matrix_generated"


def test_generate_fluid_typography_clamp_matrix(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    clamp_mat = business_metrics.generate_fluid_typography_clamp_matrix(
        conn, organization_id=parent_id, min_vw=320, max_vw=1920
    )

    assert clamp_mat["fluid_typography_clamp_id"].startswith("clamp_")
    assert clamp_mat["organization_id"] == parent_id
    assert clamp_mat["min_viewport_px"] == 320
    assert "clamp" in clamp_mat["h1_clamp_expression"]
    assert clamp_mat["status"] == "fluid_typography_clamp_generated"


def test_generate_accessible_keyboard_focus_architecture(tmp_path):
    conn, parent_id = _setup_test_db(tmp_path)

    focus_arch = security_audit.generate_accessible_keyboard_focus_architecture(
        conn, organization_id=parent_id, focus_style="glowing_accent_ring"
    )

    assert focus_arch["accessible_focus_architecture_id"].startswith("a11yfocus_")
    assert focus_arch["organization_id"] == parent_id
    assert focus_arch["focus_style"] == "glowing_accent_ring"
    assert focus_arch["keyboard_navigation_trap_enabled"] is True
    assert focus_arch["wcag_accessibility_standard"] == "WCAG_2_1_AAA"
    assert focus_arch["status"] == "accessible_focus_architecture_generated"
