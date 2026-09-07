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
