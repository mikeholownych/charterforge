"""Specialist workforce routing: dispatch-time roster match (aux LLM,
fail-open) + durable per-assignee learnings injected at worker spawn.

Routing is opt-in (kanban.specialist_routing) and never blocks dispatch:
any failure falls back to the existing default_assignee path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def board_env(tmp_path, monkeypatch):
    """A kanban store + roster in a temp HERMES_HOME."""
    import sqlite3
    import hermes_cli.kanban_db as kb

    home = tmp_path / "hermes-home"
    (home / "kanban").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    # Premise adaptation: kanban_db.connect() takes a Path, not a str
    # (kanban_db.py:2127 does path.parent.mkdir).
    conn = kb.connect(home / "kanban" / "board.db")
    conn.row_factory = sqlite3.Row
    yield home, conn
    conn.close()


ROSTER = {
    "profiles": [
        {"name": "frontend-dev", "description": "React, TypeScript, UI work"},
        {"name": "backend-dev", "description": "APIs, databases, Python"},
        {"name": "default", "description": "Generalist fallback"},
    ],
}


@pytest.fixture()
def roster(board_env):
    home, _conn = board_env
    # Premise-adapted roster: this fixture patches the roster READER in
    # route_task's module (see implementation) rather than writing a JSON
    # file, unless the real reader is file-based — adapt per the premise
    # check and note the adaptation.
    return ROSTER


def _enabled(monkeypatch):
    import hermes_cli.config as config_mod

    monkeypatch.setattr(
        config_mod, "load_config",
        lambda: {"kanban": {"specialist_routing": True,
                            "default_assignee": "default"}},
    )


class TestSpecialistRouting:
    def test_llm_pick_routes_task_to_best_fit(self, roster, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "backend-dev",
        )
        picked = ks.route_task("Add pagination to the REST API", roster)
        assert picked == "backend-dev"

    def test_unknown_pick_falls_back_to_default(self, roster, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "nonexistent-profile",
        )
        picked = ks.route_task("Do a thing", roster)
        assert picked == "default"

    def test_disabled_config_returns_none(self, roster, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        import hermes_cli.config as config_mod

        def _must_not_call(*a, **k):
            raise AssertionError("LLM must not be called when routing is disabled")

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"kanban": {"default_assignee": "default"}},
        )
        monkeypatch.setattr(ks, "_llm_pick_assignee", _must_not_call)
        assert ks.route_task("Anything", roster) is None

    def test_llm_pick_sanitized(self, roster, monkeypatch):
        """route_task receives the RAW pick; sanitization happens inside
        _llm_pick_assignee, so patch the INNER raw call (_llm_raw_pick).

        Cases: wrapping backticks/quotes/asterisks, trailing punctuation,
        multi-line replies. NOT take-first-word — profile names may
        contain spaces.
        """
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        cases = [
            ("`backend-dev`", "backend-dev"),
            ('"frontend-dev"', "frontend-dev"),
            ("'frontend-dev'", "frontend-dev"),
            ("``backend-dev``", "backend-dev"),
            ("**backend-dev**", "backend-dev"),
            ("backend-dev.", "backend-dev"),
            ("backend-dev\nbecause API.", "backend-dev"),
        ]
        for raw, expected in cases:
            monkeypatch.setattr(
                ks, "_llm_raw_pick",
                lambda task_desc, roster_entries, _raw=raw: _raw,
            )
            picked = ks.route_task("Add pagination to the REST API", roster)
            assert picked == expected, f"raw={raw!r}"

    def test_invalid_default_assignee_returns_none(self, roster, monkeypatch):
        """Returning a nonspawnable default would poison the assignment;
        the caller's existing path handles None identically with correct
        event semantics."""
        import hermes_cli.config as config_mod
        from hermes_cli import kanban_specialist as ks

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"kanban": {"specialist_routing": True,
                                "default_assignee": "ghost-profile"}},
        )
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "nonexistent",
        )
        picked = ks.route_task("Do a thing", roster)
        assert picked is None

    def test_lazy_roster_loads_from_profiles(self, board_env, monkeypatch):
        """Production path: route_task with no roster arg loads via
        kanban_decompose._build_roster."""
        from hermes_cli import kanban_specialist as ks
        import hermes_cli.kanban_decompose as kd

        _enabled(monkeypatch)
        fake_entries = [
            {"name": "backend-dev", "description": "APIs"},
            {"name": "default", "description": "Generalist"},
        ]
        monkeypatch.setattr(
            kd, "_build_roster", lambda: (fake_entries, {"backend-dev", "default"})
        )
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "backend-dev",
        )
        picked = ks.route_task("Add pagination to the REST API")  # no roster arg
        assert picked == "backend-dev"

    def test_llm_error_falls_back(self, roster, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        def boom(*a, **k):
            raise RuntimeError("provider down")
        monkeypatch.setattr(ks, "_llm_pick_assignee", boom)
        picked = ks.route_task("Add pagination to the REST API", roster)
        assert picked == "default"

    def test_empty_roster_returns_none(self, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        assert ks.route_task("Anything", {"profiles": []}) is None
