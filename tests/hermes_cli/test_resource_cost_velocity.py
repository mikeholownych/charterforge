"""Unit tests for token cost velocity detection and model tier recommendation."""

from __future__ import annotations

import sqlite3

from hermes_cli import objectives_db, resource_budget


def test_cost_velocity_detects_high_burn_and_recommends_flash_tier(tmp_path):
    conn = objectives_db.connect(tmp_path / "authority.db")
    resource_budget.ensure_schema(conn)

    obj_id = "obj_cost_velocity_test_001"

    # Record compute usage: 2 cycles, 120,000 total tokens -> 60,000 tokens/cycle
    for _ in range(2):
        resource_budget.record_cycle(
            conn,
            objective_id=obj_id,
            actions=2,
            input_tokens=50000,
            output_tokens=10000,
            estimated_compute_cost_minor=25,
        )

    result = resource_budget.check_cost_velocity_and_recommend_tier(
        conn, obj_id, token_velocity_threshold_per_cycle=50000
    )

    assert result["high_velocity"] is True
    assert result["recommended_model_tier"] == "flash"
    assert result["avg_tokens_per_cycle"] == 60000


def test_cost_velocity_returns_standard_tier_for_normal_burn(tmp_path):
    conn = objectives_db.connect(tmp_path / "authority.db")
    resource_budget.ensure_schema(conn)

    obj_id = "obj_normal_velocity_test_002"

    # Record compute usage: 5 cycles, 50,000 total tokens -> 10,000 tokens/cycle
    for _ in range(5):
        resource_budget.record_cycle(
            conn,
            objective_id=obj_id,
            actions=1,
            input_tokens=8000,
            output_tokens=2000,
            estimated_compute_cost_minor=4,
        )

    result = resource_budget.check_cost_velocity_and_recommend_tier(
        conn, obj_id, token_velocity_threshold_per_cycle=50000
    )

    assert result["high_velocity"] is False
    assert result["recommended_model_tier"] == "standard"
    assert result["avg_tokens_per_cycle"] == 10000
