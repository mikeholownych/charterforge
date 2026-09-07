"""Multiplex dotenv isolation + external-secret hydration lifecycle.

Under a routed profile-home override in a multiplex gateway, load_hermes_dotenv
must hydrate the profile's external secret sources into the profile's PRIVATE
snapshot (no os.environ mutation, no sibling leakage), honor
load_external_secrets=False on BOTH branches, and never crash when the early
recovery phase defers hydration. Unscoped startup keeps the normal path.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture()
def multiplex_routed(monkeypatch, tmp_path):
    """Multiplex active + routed profile-home override."""
    from agent import secret_scope

    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", True)

    from hermes_constants import _HERMES_HOME_OVERRIDE, _UNSET
    _HERMES_HOME_OVERRIDE.set(str(tmp_path))
    yield tmp_path
    _HERMES_HOME_OVERRIDE.set(_UNSET)


@pytest.fixture()
def no_external_sources(monkeypatch):
    """A profile with a .env but no configured external secret sources."""
    applied = []

    def fake_apply(home_path):
        applied.append(Path(home_path))
        return {}

    monkeypatch.setattr(
        "hermes_cli.env_loader._apply_external_secret_sources", fake_apply
    )
    monkeypatch.setattr(
        "hermes_cli.env_loader._hydrate_profile_secret_sources",
        lambda home: {" hydrated": [home]},
    )
    return applied


def test_multiplex_routed_load_does_not_mutate_environ(
    multiplex_routed, no_external_sources, monkeypatch
):
    """A routed profile's .env must NOT be copied into os.environ."""
    home = multiplex_routed
    (home / ".env").write_text("ROUTED_PROFILE_SECRET=super-secret-value\n")

    sentinel = os.environ.get("ROUTED_PROFILE_SECRET")

    from hermes_cli.env_loader import load_hermes_dotenv

    loaded = load_hermes_dotenv(hermes_home=home)

    assert loaded == []  # dotenv files are NOT applied on the routed branch
    assert os.environ.get("ROUTED_PROFILE_SECRET") == sentinel


def test_multiplex_routed_hydrates_private_snapshot(
    multiplex_routed, no_external_sources
):
    """load_external_secrets=True hydrates the profile-private mapping."""
    hydrated = []

    from hermes_cli import env_loader

    monkey_default = None  # fixture already stubbed _hydrate_profile_secret_sources

    # Re-stub to a recorder for this test (the fixture stub returns a marker).
    import pytest as _pytest  # noqa: F401

    home = multiplex_routed
    # The fixture's stub records nothing; drive hydrate directly through the
    # branch by stubbing a recorder here via the module global.
    orig = env_loader._hydrate_profile_secret_sources
    env_loader._hydrate_profile_secret_sources = lambda h: hydrated.append(h) or {}
    try:
        env_loader.load_hermes_dotenv(hermes_home=home)
    finally:
        env_loader._hydrate_profile_secret_sources = orig

    assert hydrated == [home]


def test_multiplex_routed_honors_load_external_secrets_false(
    multiplex_routed, monkeypatch
):
    """load_external_secrets=False must skip hydration on the routed branch."""
    hydrated = []
    from hermes_cli import env_loader

    orig = env_loader._hydrate_profile_secret_sources
    env_loader._hydrate_profile_secret_sources = lambda h: hydrated.append(h) or {}
    try:
        env_loader.load_hermes_dotenv(hermes_home=multiplex_routed, load_external_secrets=False)
    finally:
        env_loader._hydrate_profile_secret_sources = orig

    assert hydrated == []


def test_ordinary_path_honors_load_external_secrets_false(
    monkeypatch, tmp_path
):
    """The unscoped startup path must also honor load_external_secrets=False."""
    from agent import secret_scope

    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", False)

    applied = []
    monkeypatch.setattr(
        "hermes_cli.env_loader._apply_external_secret_sources",
        lambda home: applied.append(Path(home)),
    )

    from hermes_cli.env_loader import load_hermes_dotenv

    load_hermes_dotenv(hermes_home=tmp_path, load_external_secrets=False)

    assert applied == []


def test_recovery_skip_defers_hydration_without_crash(
    multiplex_routed, monkeypatch
):
    """When early recovery defers external sources, the routed branch returns
    cleanly (no NameError on home_path, no hydration attempt)."""
    from hermes_cli import _early_recovery, env_loader

    monkeypatch.setattr(
        _early_recovery, "_should_skip_external_secret_sources", lambda: True
    )
    called = []
    orig = env_loader._hydrate_profile_secret_sources
    env_loader._hydrate_profile_secret_sources = lambda h: called.append(h) or {}
    try:
        loaded = env_loader.load_hermes_dotenv(hermes_home=multiplex_routed)
    finally:
        env_loader._hydrate_profile_secret_sources = orig

    assert loaded == []
    assert called == []


def test_recovery_skip_flag_tracks_update_retry_state(monkeypatch):
    """_should_skip_external_secret_sources reflects the updater's recovery
    state, not a constant."""
    from hermes_cli import _early_recovery

    monkeypatch.setattr(_early_recovery, "_UPDATE_RETRY_RECOVERED", False)
    assert _early_recovery._should_skip_external_secret_sources() is False
    monkeypatch.setattr(_early_recovery, "_UPDATE_RETRY_RECOVERED", True)
    assert _early_recovery._should_skip_external_secret_sources() is True


def test_unscoped_startup_loads_dotenv_normally(monkeypatch, tmp_path):
    """Without multiplexing, the ordinary path loads .env into os.environ."""
    from agent import secret_scope

    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", False)
    monkeypatch.setattr(
        "hermes_cli.env_loader._apply_external_secret_sources", lambda home: None
    )
    monkeypatch.setattr("hermes_cli.env_loader._apply_managed_env", lambda: None)

    (tmp_path / ".env").write_text("UNSCOPED_TEST_KEY=normal-path\n")

    from hermes_cli.env_loader import load_hermes_dotenv

    loaded = load_hermes_dotenv(hermes_home=tmp_path)

    assert len(loaded) == 1
    assert os.environ.get("UNSCOPED_TEST_KEY") == "normal-path"
