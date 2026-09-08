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


class TestLearnings:
    def test_write_and_read_learnings(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        ks.record_learning(str(kanban_dir), "backend-dev",
                           "The API uses cursor pagination, not offsets.")
        text = ks.load_learnings(str(kanban_dir), "backend-dev")
        assert "cursor pagination" in text

    def test_learnings_scoped_per_assignee(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        ks.record_learning(str(kanban_dir), "backend-dev", "api note")
        ks.record_learning(str(kanban_dir), "frontend-dev", "ui note")
        assert "api note" in ks.load_learnings(str(kanban_dir), "backend-dev")
        assert "api note" not in ks.load_learnings(str(kanban_dir), "frontend-dev")

    def test_learnings_append_with_timestamp(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        ks.record_learning(str(kanban_dir), "backend-dev", "note one")
        ks.record_learning(str(kanban_dir), "backend-dev", "note two")
        text = ks.load_learnings(str(kanban_dir), "backend-dev")
        assert "note one" in text and "note two" in text
        assert "[2" in text  # timestamped entries

    def test_empty_text_is_noop(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        assert ks.record_learning(str(kanban_dir), "backend-dev", "   ") is False
        assert ks.load_learnings(str(kanban_dir), "backend-dev") == ""

    def test_invalid_assignee_refused(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        assert ks.record_learning(str(kanban_dir), "../evil", "x") is False
        assert ks.record_learning(str(kanban_dir), "", "x") is False
        assert ks.load_learnings(str(kanban_dir), "../evil") == ""

    def test_learnings_capped_at_tail(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        for i in range(60):
            ks.record_learning(str(kanban_dir), "backend-dev", f"note {i}")
        text = ks.load_learnings(str(kanban_dir), "backend-dev")
        assert "note 0" not in text  # head evicted
        assert "note 59" in text     # tail retained

    def test_build_worker_prompt_includes_learnings(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        kanban_dir = home / "kanban"
        ks.record_learning(str(kanban_dir), "backend-dev",
                           "Cursor pagination only.")
        prompt = ks.build_worker_prompt(
            "Add pagination.", "backend-dev", kanban_dir,
        )
        assert "Add pagination." in prompt
        assert "Cursor pagination only." in prompt
        assert prompt.find("Add pagination.") < prompt.find("Cursor pagination only.")

    def test_build_worker_prompt_empty_learnings_unchanged(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        prompt = ks.build_worker_prompt("Just the task.", "nobody", home / "kanban")
        assert prompt == "Just the task."


class TestRoutingEnabled:
    """``routing_enabled`` — the shared config seam the dispatcher wiring
    uses to skip ``route_task`` entirely (lock-held) when routing is off."""

    def test_reads_specialist_routing_flag(self, monkeypatch):
        import hermes_cli.config as config_mod
        from hermes_cli import kanban_specialist as ks

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"kanban": {"specialist_routing": True}},
        )
        assert ks.routing_enabled() is True

    def test_disabled_config_reads_false(self, monkeypatch):
        import hermes_cli.config as config_mod
        from hermes_cli import kanban_specialist as ks

        monkeypatch.setattr(
            config_mod, "load_config", lambda: {"kanban": {}},
        )
        assert ks.routing_enabled() is False

    def test_config_failure_is_fail_closed(self, monkeypatch):
        import hermes_cli.config as config_mod
        from hermes_cli import kanban_specialist as ks

        def boom():
            raise RuntimeError("config unreadable")

        monkeypatch.setattr(config_mod, "load_config", boom)
        assert ks.routing_enabled() is False


class TestDispatcherWiring:
    """Dispatcher tick wiring: unassigned ready tasks that would fall
    through to ``kanban.default_assignee`` get a specialist routing chance
    first. Contracts: routed+audited, failure→default, per-tick breaker
    caps the auxiliary LLM at 1 call, explicit assignments never touched.

    Premise adaptations from the real code:
    - ``_dispatch_once_locked`` lives in kanban_db_dispatch.py (not
      kanban_db.py, which keeps a legacy copy); called directly here.
    - ``create_task`` is keyword-only with ``created_by`` (no ``author``);
      a fresh parentless task is born ``ready`` so it flows straight into
      the ready loop.
    - ``get_task`` returns a ``Task`` dataclass → attribute access.
    - ``assign_task(conn, task_id, profile)`` has no ``actor`` kwarg.
    - The spawn seam is the ``_default_spawn`` module global (tests patch
      it with a recorder; passing ``spawn_fn=`` is the equivalent seam).
    - The lazy roster (``_load_roster`` → profiles) is empty in a temp
      HERMES_HOME, so wiring tests patch ``ks._load_roster``.
    - ``_memory_pressure_level`` is pinned to "ok" so a busy host can't
      cap the tick at 0/1 spawns and break the two-task breaker test.
    """

    def _ready_unassigned_task(self, conn):
        import hermes_cli.kanban_db as kb

        return kb.create_task(
            conn, title="Add REST pagination", body="API pagination work",
            created_by="test",
        )

    def test_unassigned_task_routed_and_audited(
        self, board_env, all_assignees_spawnable, monkeypatch
    ):
        """Unassigned ready task → routed to backend-dev → applied with
        source=kanban.specialist_routing → audit comment recorded."""
        import hermes_cli.kanban_db as kb
        from hermes_cli import kanban_db_dispatch as kd
        from hermes_cli import kanban_specialist as ks

        home, conn = board_env
        _enabled(monkeypatch)
        monkeypatch.setattr(ks, "_load_roster", lambda: ROSTER)
        task_id = self._ready_unassigned_task(conn)
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "backend-dev",
        )
        monkeypatch.setattr(kd, "_memory_pressure_level", lambda sample=None: "ok")
        spawns = []
        monkeypatch.setattr(
            kd, "_default_spawn", lambda *a, **k: spawns.append(a) or 0,
        )
        # kanban_ops (the daemon) reads kanban.default_assignee from config
        # and passes it into the tick; mirror that here (_enabled sets it to
        # "default").
        kd._dispatch_once_locked(conn, default_assignee="default")
        refreshed = kb.get_task(conn, task_id)
        assert refreshed is not None
        assert refreshed.assignee == "backend-dev"
        events = conn.execute(
            "SELECT payload FROM task_events WHERE task_id=? AND kind='assigned'",
            (task_id,),
        ).fetchall()
        assert any(
            json.loads(row["payload"]).get("source") == "kanban.specialist_routing"
            for row in events
        )
        comments = conn.execute(
            "SELECT author, body FROM task_comments WHERE task_id=? AND "
            "body LIKE 'specialist route%'", (task_id,),
        ).fetchall()
        assert len(comments) == 1
        assert comments[0]["author"] == "dispatcher"
        assert comments[0]["body"] == "specialist route: backend-dev"

    def test_routing_failure_falls_back_to_default(
        self, board_env, all_assignees_spawnable, monkeypatch
    ):
        from hermes_cli import kanban_db_dispatch as kd
        from hermes_cli import kanban_specialist as ks

        home, conn = board_env
        _enabled(monkeypatch)
        # default_assignee = "default" (in roster) via _enabled's config.
        monkeypatch.setattr(ks, "_load_roster", lambda: ROSTER)
        task_id = self._ready_unassigned_task(conn)
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "nonexistent",
        )
        monkeypatch.setattr(kd, "_memory_pressure_level", lambda sample=None: "ok")
        spawns = []
        monkeypatch.setattr(
            kd, "_default_spawn", lambda *a, **k: spawns.append(a) or 0,
        )
        # kanban_ops (the daemon) reads kanban.default_assignee from config
        # and passes it into the tick; mirror that here (_enabled sets it to
        # "default").
        kd._dispatch_once_locked(conn, default_assignee="default")
        import hermes_cli.kanban_db as kb

        refreshed = kb.get_task(conn, task_id)
        assert refreshed is not None
        assert refreshed.assignee == "default"
        # The fallback came from the DEFAULT path, not a dressed-up
        # specialist routing: source stays kanban.default_assignee and no
        # specialist audit comment is written.
        events = conn.execute(
            "SELECT payload FROM task_events WHERE task_id=? AND kind='assigned'",
            (task_id,),
        ).fetchall()
        assert any(
            json.loads(row["payload"]).get("source") == "kanban.default_assignee"
            for row in events
        )
        assert not conn.execute(
            "SELECT 1 FROM task_comments WHERE task_id=? AND "
            "body LIKE 'specialist route%'", (task_id,),
        ).fetchone()

    def test_breaker_caps_llm_calls_per_tick(
        self, board_env, all_assignees_spawnable, monkeypatch
    ):
        """First routing failure trips the per-tick breaker: the second
        unassigned task in the same tick gets NO LLM call."""
        import hermes_cli.kanban_db as kb
        from hermes_cli import kanban_db_dispatch as kd
        from hermes_cli import kanban_specialist as ks

        home, conn = board_env
        _enabled(monkeypatch)
        monkeypatch.setattr(ks, "_load_roster", lambda: ROSTER)
        t1 = self._ready_unassigned_task(conn)
        t2 = self._ready_unassigned_task(conn)
        calls = []

        def counting_pick(task_desc, roster_entries):
            calls.append(1)
            return "nonexistent"  # always unknown → always fails validation

        monkeypatch.setattr(ks, "_llm_pick_assignee", counting_pick)
        monkeypatch.setattr(kd, "_memory_pressure_level", lambda sample=None: "ok")
        spawns = []
        monkeypatch.setattr(
            kd, "_default_spawn", lambda *a, **k: spawns.append(a) or 0,
        )
        # kanban_ops (the daemon) reads kanban.default_assignee from config
        # and passes it into the tick; mirror that here (_enabled sets it to
        # "default").
        kd._dispatch_once_locked(conn, default_assignee="default")
        assert len(calls) == 1  # breaker: 2 tasks, 1 LLM call
        # Both tasks still reach the default path (fallback semantics intact).
        r1 = kb.get_task(conn, t1)
        r2 = kb.get_task(conn, t2)
        assert r1 is not None and r2 is not None
        assert r1.assignee == "default" and r2.assignee == "default"

    def test_explicit_assignment_never_overridden(
        self, board_env, all_assignees_spawnable, monkeypatch
    ):
        import hermes_cli.kanban_db as kb
        from hermes_cli import kanban_db_dispatch as kd
        from hermes_cli import kanban_specialist as ks

        home, conn = board_env
        _enabled(monkeypatch)
        monkeypatch.setattr(ks, "_load_roster", lambda: ROSTER)
        task_id = self._ready_unassigned_task(conn)
        kb.assign_task(conn, task_id, "frontend-dev")
        llm_called = []
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: llm_called.append(1) or "backend-dev",
        )
        monkeypatch.setattr(kd, "_memory_pressure_level", lambda sample=None: "ok")
        spawns = []
        monkeypatch.setattr(
            kd, "_default_spawn", lambda *a, **k: spawns.append(a) or 0,
        )
        # kanban_ops (the daemon) reads kanban.default_assignee from config
        # and passes it into the tick; mirror that here (_enabled sets it to
        # "default").
        kd._dispatch_once_locked(conn, default_assignee="default")
        assert llm_called == []  # routing skipped for explicitly assigned
        refreshed = kb.get_task(conn, task_id)
        assert refreshed is not None
        assert refreshed.assignee == "frontend-dev"
