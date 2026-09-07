"""Autonomous blocked-outcome policy: charter contract + runtime behavior.

This module pins the charter contract; runtime application tests are added by later tasks in the same plan.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from hermes_cli import objective_policy


def _charter(**overrides):
    charter = {
        "enabled": True,
        "operating_mode": "autonomous",
        "max_autonomous_risk": "medium",
        "permit_ttl_seconds": 300,
        "runtime_host": "gateway",
        "blocked_outcome_policy": {
            "mode": "autonomous",
            "max_replan_attempts": 2,
            "replan_backoff_seconds": 60,
            "abandon_after_max": True,
        },
    }
    charter.update(overrides)
    return charter


class TestCharterValidation:
    def test_valid_autonomous_policy_accepted(self):
        objective_policy.validate_charter(_charter())  # must not raise

    def test_default_missing_policy_is_advise(self):
        objective_policy.validate_charter(
            {k: v for k, v in _charter().items() if k != "blocked_outcome_policy"}
        )

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError, match="blocked_outcome_policy.mode"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={"mode": "yolo"})
            )

    def test_nonpositive_attempts_rejected(self):
        with pytest.raises(ValueError, match="max_replan_attempts"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous", "max_replan_attempts": 0
                })
            )

    def test_negative_backoff_rejected(self):
        with pytest.raises(ValueError, match="replan_backoff_seconds"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous",
                    "max_replan_attempts": 1,
                    "replan_backoff_seconds": -5,
                })
            )

    def test_abandon_after_max_must_be_bool(self):
        with pytest.raises(ValueError, match="abandon_after_max"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous",
                    "max_replan_attempts": 1,
                    "abandon_after_max": "yes",
                })
            )

    def test_attempts_upper_bound_pinned(self):
        objective_policy.validate_charter(
            _charter(blocked_outcome_policy={
                "mode": "autonomous", "max_replan_attempts": 25
            })
        )
        with pytest.raises(ValueError, match="max_replan_attempts"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous", "max_replan_attempts": 26
                })
            )

    def test_non_int_attempts_rejected(self):
        for bad in ("3", 2.5):
            with pytest.raises(ValueError, match="max_replan_attempts"):
                objective_policy.validate_charter(
                    _charter(blocked_outcome_policy={
                        "mode": "autonomous", "max_replan_attempts": bad
                    })
                )

    def test_non_int_backoff_rejected(self):
        for bad in ("60", 45.5, [10]):
            with pytest.raises(ValueError, match="replan_backoff_seconds"):
                objective_policy.validate_charter(
                    _charter(blocked_outcome_policy={
                        "mode": "autonomous",
                        "max_replan_attempts": 1,
                        "replan_backoff_seconds": bad,
                    })
                )

    def test_mode_whitespace_is_coerced(self):
        objective_policy.validate_charter(
            _charter(blocked_outcome_policy={"mode": "  autonomous  "})
        )


# Adaptation vs. the planned fixture: objectives_db.connect() resolves its
# path arg (":memory:" would become a literal <cwd>/:memory: file), so the
# store is opened against a per-test tmp_path instead.
@pytest.fixture()
def conn(tmp_path):
    from hermes_cli import objectives_db

    conn = objectives_db.connect(tmp_path / "objectives.db")
    conn.row_factory = sqlite3.Row
    return conn


def _make_objective(conn):
    from hermes_cli import objectives_db as db

    return db.create_objective(
        conn,
        organization_id="__unscoped__",
        desired_outcome="prove the outcome",
        originator="human_operator:setup",
        owner="employee:ceo-1",
        constraints=[],
        authority_scope={"capabilities": []},
        success_criteria=[{"verifier": "v", "params": {}}],
        termination_conditions=[],
        permitted_systems=[],
        prohibited_actions=[],
        max_spend_minor=1000,
        currency="USD",
        expires_at=None,
    )


class TestReplanCounter:
    def test_column_exists_and_defaults_zero(self, conn):
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_increment_and_reset(self, conn):
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        assert db.record_blocked_replan(conn, obj.id) == 1
        assert db.record_blocked_replan(conn, obj.id) == 2
        db.reset_blocked_replan(conn, obj.id)
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_counter_is_scoped_per_objective(self, conn):
        from hermes_cli import objectives_db as db

        a = _make_objective(conn)
        b = _make_objective(conn)
        db.record_blocked_replan(conn, a.id)
        assert db.blocked_replan_attempts(conn, b.id) == 0

    # Adaptation vs. the planned test: "abandoned" is not reachable from the
    # "proposed" state (_TRANSITIONS); "cancelled" is reachable and terminal.
    def test_reset_on_terminal_transition(self, conn):
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        db.record_blocked_replan(conn, obj.id)
        db.transition_objective(conn, obj.id, "cancelled", actor="test")
        assert db.blocked_replan_attempts(conn, obj.id) == 0
