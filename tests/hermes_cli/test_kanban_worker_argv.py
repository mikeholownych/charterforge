"""Kanban worker spawn argv / Task reasoning_effort contract tests.

The dispatcher's ``_worker_argv`` runs on every real spawn and reads
``task.reasoning_effort`` (upstream parity). The ``Task`` dataclass must
carry that field — with the schema counterpart restored to match upstream —
so a plain task can never AttributeError the dispatch loop and block every
kanban dispatch.
"""

import sqlite3

import pytest

from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_dispatch as kd


@pytest.fixture
def conn(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    (home / "kanban").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    c = kb.connect(home / "kanban" / "board.db")
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _real_task(conn) -> kb.Task:
    """A task created via the real API and read back the way the dispatcher does."""
    task_id = kb.create_task(conn, title="T", body="B", created_by="test")
    return kb.get_task(conn, task_id)


def test_worker_argv_does_not_crash_on_plain_task(conn):
    """_worker_argv must not AttributeError on a Task — every real spawn
    depends on it (kanban dispatch was blocked by exactly this crash)."""
    task = _real_task(conn)
    argv = kd._worker_argv(task, "worker-profile", None)
    assert any("work kanban task" in str(a) for a in argv)


def test_worker_argv_emits_reasoning_flag_when_set(conn):
    """When the task carries a reasoning effort, the worker argv pins it."""
    task = _real_task(conn)
    task.reasoning_effort = "high"
    argv = kd._worker_argv(task, "worker-profile", None)
    assert argv[argv.index("--reasoning") + 1] == "high"


def test_task_roundtrips_reasoning_effort_from_row(conn):
    """from_row maps the reasoning_effort column (None when unset/absent)."""
    task = _real_task(conn)
    assert task.reasoning_effort is None
    conn.execute(
        "UPDATE tasks SET reasoning_effort = ? WHERE id = ?", ("medium", task.id)
    )
    reloaded = kb.get_task(conn, task.id)
    assert reloaded.reasoning_effort == "medium"


def test_migrated_legacy_db_has_reasoning_effort_column(conn):
    """Legacy DBs get the additive column via _migrate_add_optional_columns,
    converging on the fresh-schema shape."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    assert "reasoning_effort" in cols
