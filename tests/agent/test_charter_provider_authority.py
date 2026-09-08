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


# ── Choke-point filtering (Task 2) ─────────────────────────────────────────


@pytest.fixture()
def restricted_chain(monkeypatch):
    """Charter boundary {nous} + objective_planner chain [openrouter, nous]."""
    import hermes_cli.config as config_mod

    chain_cfg = {"auxiliary": {"objective_planner": {"fallback_chain": [
        {"provider": "OpenRouter", "model": "m-open"},
        {"provider": "nous", "model": "m-nous"},
    ]}}}
    monkeypatch.setattr(
        config_mod, "load_config_readonly", lambda: chain_cfg
    )
    # Boundary via the policy module the filter reads.
    import hermes_cli.objective_policy as op

    monkeypatch.setattr(
        op, "authorized_auxiliary_providers",
        lambda charter=None: frozenset({"nous"}),
    )
    return chain_cfg


@pytest.fixture()
def resolve_recorder(monkeypatch):
    called = []

    def fake_resolve(entry):
        called.append(str(entry.get("provider", "")).strip())
        client = type("C", (), {"base_url": f"https://{entry.get('provider')}.test"})()
        return client, entry.get("model")

    from agent import auxiliary_client as aux

    monkeypatch.setattr(aux, "_resolve_fallback_entry", fake_resolve)
    monkeypatch.setattr(aux, "_context_too_small", lambda *a, **k: None)
    return called


class TestChokePointFiltering:
    def test_task_chain_skips_unauthorized_entry(
        self, restricted_chain, resolve_recorder
    ):
        """Mixed-case unauthorized entry ('OpenRouter') is skipped WITHOUT
        being resolved; the authorized lower-case entry wins. Case-insensitive
        comparison via the shared predicate (R1)."""
        from agent import auxiliary_client as aux

        client, model, label = aux._try_configured_fallback_chain(
            "objective_planner", "auto", reason="test"
        )
        assert resolve_recorder == ["nous"]
        assert client is not None
        assert "nous" in label

    def test_no_authorized_candidate_raises_fail_closed(
        self, monkeypatch, resolve_recorder
    ):
        """All entries unauthorized → typed raise with attempted evidence —
        NOT a silent (None, None, '')."""
        import hermes_cli.config as config_mod
        from agent import auxiliary_client as aux

        monkeypatch.setattr(
            config_mod, "load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {"fallback_chain": [
                {"provider": "openrouter"},
            ]}}},
        )
        import hermes_cli.objective_policy as op

        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: frozenset({"nous"}),
        )
        with pytest.raises(aux.AuxiliaryProviderNotAuthorized) as excinfo:
            aux._try_configured_fallback_chain(
                "objective_planner", "auto", reason="test"
            )
        assert "openrouter" in excinfo.value.attempted
        assert excinfo.value.authorized == {"nous"}

    def test_authorized_but_unbuildable_is_normal_exhaustion(
        self, restricted_chain, monkeypatch
    ):
        """An authorized entry that fails to BUILD a client is ordinary chain
        exhaustion (no raise) — the authority refusal fires only when every
        ATTEMPTED entry was unauthorized."""
        from agent import auxiliary_client as aux

        def broken_resolve(entry):
            if entry.get("provider") == "nous":
                return None, None  # build failure on the authorized entry
            return type("C", (), {"base_url": "x"})(), entry.get("model")

        monkeypatch.setattr(aux, "_resolve_fallback_entry", broken_resolve)
        monkeypatch.setattr(aux, "_context_too_small", lambda *a, **k: None)
        client, model, label = aux._try_configured_fallback_chain(
            "objective_planner", "auto", reason="test"
        )
        assert client is None  # exhausted, not refused

    def test_vacuous_boundary_fails_closed(self, monkeypatch):
        """Empty frozenset boundary (authorize nothing) must refuse — the
        `is not None` contract (R2)."""
        import hermes_cli.config as config_mod
        from agent import auxiliary_client as aux

        monkeypatch.setattr(
            config_mod, "load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {"fallback_chain": [
                {"provider": "nous"},
            ]}}},
        )
        import hermes_cli.objective_policy as op

        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: frozenset(),  # vacuous = authorize nothing
        )
        with pytest.raises(aux.AuxiliaryProviderNotAuthorized):
            aux._try_configured_fallback_chain(
                "objective_planner", "auto", reason="test"
            )

    def test_backend_skipped_authorized_entry_semantics(
        self, monkeypatch, resolve_recorder
    ):
        """[unauthorized, authorized-but-backend-skipped] under boundary {nous}:
        the kept-but-skipped authorized entry never reaches `tried`, so the
        typed refusal fires (documented semantics — blocks fall-through into
        unfiltered chains in the partial-coverage state)."""
        import hermes_cli.config as config_mod
        from agent import auxiliary_client as aux

        monkeypatch.setattr(
            config_mod, "load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {"fallback_chain": [
                {"provider": "openrouter", "model": "m-open"},
                {"provider": "nous", "model": "m-nous"},
            ]}}},
        )
        import hermes_cli.objective_policy as op

        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: frozenset({"nous"}),
        )
        # Simulate the nous entry being backend-skipped (e.g. it IS the
        # failed primary): _failed_backend_skip returns True for it.
        monkeypatch.setattr(
            aux, "_failed_backend_skip",
            lambda failed_provider, failed_model: (
                lambda provider, model, base_url="": provider.lower() == "nous"
            ),
        )
        with pytest.raises(aux.AuxiliaryProviderNotAuthorized) as excinfo:
            aux._try_configured_fallback_chain(
                "objective_planner", "nous", reason="test",
                failed_model="m-nous",
            )
        assert excinfo.value.attempted == ["openrouter"]
        assert resolve_recorder == []  # nothing was resolved

    def test_no_charter_is_unchanged(self, monkeypatch, resolve_recorder):
        """Boundary None → original behavior: both entries resolved in
        order, first success returns."""
        import hermes_cli.config as config_mod
        from agent import auxiliary_client as aux

        monkeypatch.setattr(
            config_mod, "load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {"fallback_chain": [
                {"provider": "openrouter", "model": "m-open"},
                {"provider": "nous", "model": "m-nous"},
            ]}}},
        )
        import hermes_cli.objective_policy as op

        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: None,
        )
        client, model, label = aux._try_configured_fallback_chain(
            "objective_planner", "auto", reason="test"
        )
        assert resolve_recorder == ["openrouter"]
        assert client is not None
        assert "openrouter" in label


class TestPrimaryBoundary:
    def test_auto_route_pinned_unauthorized_primary_raises(self, monkeypatch):
        """Auto route with a pinned unauthorized wire primary → typed raise
        before any client build."""
        from agent import auxiliary_client as aux
        import hermes_cli.config as config_mod
        import hermes_cli.objective_policy as op

        monkeypatch.setattr(config_mod, "load_config_readonly", lambda: {})
        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: frozenset({"nous"}),
        )
        # Stub the route target to return a pinned unauthorized provider.
        monkeypatch.setattr(
            aux, "_main_route_target",
            lambda runtime, task: ("openrouter", "m", "https://x", "key", None),
        )
        # If the raise happened before _try_main_provider_route, this must
        # never be reached; explode if it is.
        monkeypatch.setattr(
            aux, "_try_main_provider_route",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("client must not be built for unauthorized primary")
            ),
        )
        with pytest.raises(aux.AuxiliaryProviderNotAuthorized) as excinfo:
            aux._resolve_auto_route({}, task="objective_planner")
        assert excinfo.value.attempted == ["openrouter"]

    def test_explicit_provider_unauthorized_raises(self, monkeypatch):
        """auxiliary.<task>.provider pinned to an unauthorized provider →
        typed raise at the explicit branch of _resolve_call_client, no client
        build (resolve_provider_client never called)."""
        from agent import auxiliary_client as aux
        import hermes_cli.config as config_mod
        import hermes_cli.objective_policy as op

        monkeypatch.setattr(config_mod, "load_config_readonly", lambda: {})
        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: frozenset({"nous"}),
        )
        monkeypatch.setattr(
            aux, "resolve_provider_client",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError(
                    "client must not be built for unauthorized explicit primary"
                )
            ),
        )
        with pytest.raises(aux.AuxiliaryProviderNotAuthorized) as excinfo:
            aux._resolve_call_client(
                task="objective_planner", provider="openrouter", model="m",
                base_url=None, api_key=None,
                resolved_provider="openrouter", resolved_model="m",
                resolved_base_url=None, resolved_api_key=None,
                resolved_api_mode=None, main_runtime=None, async_mode=False,
            )
        assert excinfo.value.attempted == ["openrouter"]
        assert excinfo.value.authorized == {"nous"}
