"""Charter-scoped auxiliary provider authority.

Under an agentic charter declaring authorized_providers, auxiliary LLM calls
are restricted to those providers — fail-closed — so governed planning and
judging never silently route to an operator-unauthorized backend.
"""
from __future__ import annotations

import pytest

from hermes_cli import objective_policy


class TestAuthorizedAuxiliaryProviders:
    def test_absent_charter_returns_none(self):
        assert objective_policy.authorized_auxiliary_providers({}) is None

    def test_disabled_charter_returns_none(self):
        charter = {"enabled": False,
                   "authorized_providers": ["openrouter"]}
        assert objective_policy.authorized_auxiliary_providers(charter) is None

    def test_nonempty_list_normalized(self):
        charter = {"enabled": True,
                   "authorized_providers": ["OpenRouter", " nous ", "NOUS"]}
        assert objective_policy.authorized_auxiliary_providers(charter) == {
            "openrouter", "nous"
        }

    def test_empty_list_means_no_restriction(self):
        charter = {"enabled": True, "authorized_providers": []}
        assert objective_policy.authorized_auxiliary_providers(charter) is None

    def test_vacuous_list_authorizes_nothing(self):
        """A non-empty list of whitespace entries returns an empty frozenset
        (authorize nothing, fail-closed) — NOT None (unrestricted). Raw
        runtime config is not pre-validated, so this semantics is load-bearing."""
        charter = {"enabled": True, "authorized_providers": ["  ", ""]}
        assert objective_policy.authorized_auxiliary_providers(charter) == frozenset()

    def test_validate_charter_accepts_valid_list(self):
        objective_policy.validate_charter({
            "enabled": True, "operating_mode": "autonomous",
            "max_autonomous_risk": "medium", "permit_ttl_seconds": 300,
            "runtime_host": "gateway",
            "authorized_providers": ["nous", "openrouter"],
        })  # must not raise

    def test_non_list_rejected_by_validate_charter(self):
        with pytest.raises(ValueError, match="authorized_providers"):
            objective_policy.validate_charter({
                "enabled": True, "operating_mode": "autonomous",
                "max_autonomous_risk": "medium", "permit_ttl_seconds": 300,
                "runtime_host": "gateway",
                "authorized_providers": "openrouter",
            })

    def test_non_string_entries_rejected(self):
        with pytest.raises(ValueError, match="authorized_providers"):
            objective_policy.validate_charter({
                "enabled": True, "operating_mode": "autonomous",
                "max_autonomous_risk": "medium", "permit_ttl_seconds": 300,
                "runtime_host": "gateway",
                "authorized_providers": ["openrouter", 42],
            })


class TestTypedError:
    def test_error_carries_evidence(self):
        from agent.auxiliary_client import AuxiliaryProviderNotAuthorized

        err = AuxiliaryProviderNotAuthorized(
            task="objective_planner",
            attempted=["openrouter", "nous"],
            authorized={"nous"},
        )
        assert err.task == "objective_planner"
        assert err.attempted == ["openrouter", "nous"]
        assert err.authorized == {"nous"}
        assert "objective_planner" in str(err)
        assert "nous" in str(err)
