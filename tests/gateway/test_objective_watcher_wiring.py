"""Gateway objective-runtime watcher wiring regression.

The fork's objective-watcher integration (import + base class + supervised
spawn) was silently lost to a wholesale conflict resolution once already.
These tests pin the wiring behaviorally — mixin resolution through the MRO
and the mixin→service fail-safe chain — so a future whole-file adoption that
drops the integration fails here instead of silently disabling the governed
runtime.
"""
from __future__ import annotations

import asyncio

import pytest


def _make_runner():
    from gateway.run import GatewayRunner

    runner = GatewayRunner.__new__(GatewayRunner)
    runner._running = True
    return runner


def test_objective_watcher_mixin_resolves_through_mro():
    from gateway.objective_watcher import GatewayObjectiveWatcherMixin
    from gateway.run import GatewayRunner

    assert issubclass(GatewayRunner, GatewayObjectiveWatcherMixin)
    # The method must resolve through inheritance, not exist only on the runner.
    assert GatewayRunner.__dict__.get("_objective_runtime_watcher") is None
    assert hasattr(GatewayRunner, "_objective_runtime_watcher")


def test_disabled_charter_never_ticks(monkeypatch):
    """With ``agentic.enabled`` false the watcher returns without ever ticking."""
    import hermes_cli.config as config_mod
    from hermes_cli import objective_service, runtime_deployment

    ticks = []
    monkeypatch.setattr(
        objective_service, "tick_once", lambda *a, **k: ticks.append(1)
    )
    monkeypatch.setattr(
        config_mod, "load_config", lambda: {"agentic": {"enabled": False}}
    )
    monkeypatch.setattr(runtime_deployment, "validate_worker_role", lambda c, r: None)

    runner = _make_runner()
    asyncio.run(objective_service.gateway_watcher(runner))
    assert ticks == [], "disabled charter must never reach tick_once"


def test_role_rejection_never_ticks(monkeypatch):
    """A deployment-role rejection exits before any tick."""
    import hermes_cli.config as config_mod
    from hermes_cli import objective_service, runtime_deployment

    def _reject(charter, role):
        raise runtime_deployment.RuntimeDeploymentError("role not allowed")

    ticks = []
    monkeypatch.setattr(
        objective_service, "tick_once", lambda *a, **k: ticks.append(1)
    )
    monkeypatch.setattr(runtime_deployment, "validate_worker_role", _reject)
    monkeypatch.setattr(
        config_mod, "load_config", lambda: {"agentic": {"enabled": True}}
    )

    runner = _make_runner()
    asyncio.run(objective_service.gateway_watcher(runner))  # must return, not raise
    assert ticks == [], "role-rejected watcher must never reach tick_once"
