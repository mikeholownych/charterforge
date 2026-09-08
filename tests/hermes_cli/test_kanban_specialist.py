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

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"kanban": {"default_assignee": "default"}},
        )
        assert ks.route_task("Anything", roster) is None

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
