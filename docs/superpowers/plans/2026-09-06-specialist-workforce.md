# Specialist Workforce Routing + Durable Learnings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]` syntax for tracking.

**Goal:** The kanban dispatcher routes unassigned ready tasks to the best-fit specialist profile (auxiliary-LLM roster match, fail-open to `default_assignee`), and every worker spawn injects that assignee's durable learnings note — so specialists accumulate operational context across tasks instead of starting cold.

**Architecture:** Two pieces on the existing dispatcher rails. (1) At dispatch time, when a ready task's assignee is unset (or would fall to `default_assignee`), an auxiliary LLM call picks the best-fit profile from the live roster by task description + profile descriptions; gated by `kanban.specialist_routing` (default false); ANY failure (no roster, LLM error, unknown pick) falls back to the existing `default_assignee` path — dispatch never blocks on routing. The pick is recorded in the task's comments for audit. (2) A per-assignee learnings file (`<board>/.learnings/<assignee>.md`) injected verbatim into the worker prompt after the task body; written via `hermes kanban learn` (operator/worker CLI) and read-only at spawn. No capacity/reclaim/heartbeat changes.

**Tech Stack:** Python, existing kanban_db/kanban_db_dispatch machinery, auxiliary LLM (same contract style as kanban_decompose), pytest via `scripts/run_tests.sh`.

**Governance invariants:**
1. Routing is opt-in (`kanban.specialist_routing: true`) and fail-open: any routing error leaves the task on the existing default-assignee path. Dispatch latency without a routing decision is unchanged.
2. Roster honesty: only profiles that exist in the live roster can be picked; a picked name that doesn't resolve falls back to default_assignee (same contract as decompose).
3. Learnings are context, not authority: injection is read-only prompt text; workers cannot mutate another specialist's learnings; the learn verb is operator/worker-authorized through the existing kanban CLI surface.
4. No new HERMES_* env vars; config.yaml only.

**Files:**
- Modify: `hermes_cli/kanban_db_dispatch.py` (routing + learnings injection)
- Modify: `hermes_cli/kanban.py` (`learn` verb) + `hermes_cli/kanban_parser.py` (arg wiring)
- Create: `hermes_cli/kanban_specialist.py` (roster match + learnings store)
- Create: `tests/hermes_cli/test_kanban_specialist.py`
- Modify: `website/docs/user-guide/features/kanban.md`
- Modify: `hermes_cli/config.py` DEFAULT_CONFIG (`kanban.specialist_routing: false`)

**Premise-check directive (Task 1, before coding):** locate (a) the dispatcher's assignee-resolution point in `kanban_db_dispatch.py` where `default_assignee` is applied (#27145 comment near line 79); (b) the worker-prompt construction site (where the task title/body is rendered into the spawn prompt); (c) the roster source used by kanban_decompose for profile names + descriptions. Adapt the plan's call sites to the real code; the test contracts below are authoritative.

---

### Task 1: Specialist routing (aux-LLM roster match at dispatch)

**Files:**
- Create: `hermes_cli/kanban_specialist.py`
- Modify: `hermes_cli/kanban_db_dispatch.py`
- Test: `tests/hermes_cli/test_kanban_specialist.py`

- [ ] **Step 1: Failing tests**

```python
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
    import hermes_cli.kanban_db as kb

    home = tmp_path / "hermes-home"
    (home / "kanban").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    conn = kb.connect(str(home / "kanban" / "board.db"))
    conn.row_factory = __import__("sqlite3").Row
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
def roster(board_env, monkeypatch):
    home, _conn = board_env
    (home / "kanban" / "roster.json").write_text(
        json.dumps(ROSTER), encoding="utf-8"
    )
    # Adapt to the REAL roster source (premise check 1c) — if profiles live
    # in ~/.hermes/profiles/ metadata or kanban config, patch THAT reader.
    return ROSTER


def _enabled(monkeypatch):
    import hermes_cli.config as config_mod

    monkeypatch.setattr(
        config_mod, "load_config",
        lambda: {"kanban": {"specialist_routing": True,
                            "default_assignee": "default"}},
    )


class TestSpecialistRouting:
    def test_llm_pick_routes_task_to_best_fit(self, board_env, roster, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "backend-dev",
        )
        picked = ks.route_task("Add pagination to the REST API", roster)
        assert picked == "backend-dev"

    def test_unknown_pick_falls_back_to_default(self, board_env, roster, monkeypatch):
        """The LLM picked a profile not in the roster → default_assignee
        (same contract as kanban_decompose)."""
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        monkeypatch.setattr(
            ks, "_llm_pick_assignee",
            lambda task_desc, roster_entries: "nonexistent-profile",
        )
        picked = ks.route_task("Do a thing", roster)
        assert picked == "default"

    def test_disabled_config_returns_none(self, board_env, roster, monkeypatch):
        """specialist_routing off → route_task returns None (caller uses the
        existing default_assignee path, unchanged)."""
        from hermes_cli import kanban_specialist as ks

        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"kanban": {"default_assignee": "default"}},
        )
        assert ks.route_task("Anything", roster) is None

    def test_llm_error_falls_back(self, board_env, roster, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        def boom(*a, **k):
            raise RuntimeError("provider down")
        monkeypatch.setattr(ks, "_llm_pick_assignee", boom)
        picked = ks.route_task("Add pagination to the REST API", roster)
        assert picked == "default"

    def test_empty_roster_returns_none(self, board_env, monkeypatch):
        from hermes_cli import kanban_specialist as ks

        _enabled(monkeypatch)
        assert ks.route_task("Anything", {"profiles": []}) is None
```

- [ ] **Step 2: RED** — run `scripts/run_tests.sh tests/hermes_cli/test_kanban_specialist.py -j 1 -q`; record.

- [ ] **Step 3: Implement `hermes_cli/kanban_specialist.py`:**

```python
"""Dispatch-time specialist routing + durable per-assignee learnings.

Routing: opt-in (kanban.specialist_routing), fail-open. The auxiliary LLM
picks the best-fit profile from the live roster by task description; any
error or unknown pick falls back to the existing default_assignee path.

Learnings: per-assignee markdown notes injected verbatim into the worker
prompt at spawn. Read-only at spawn; written via `hermes kanban learn`.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PICK_SYSTEM_PROMPT = (
    "You route tasks to specialist profiles. Reply ONLY with the profile "
    "name (one word, from the roster). If none fits, reply default."
)


def _roster_entries(roster: Dict[str, Any]) -> List[Dict[str, str]]:
    entries = []
    for p in (roster or {}).get("profiles", []):
        if isinstance(p, dict) and p.get("name"):
            entries.append({
                "name": str(p["name"]),
                "description": str(p.get("description", "")),
            })
    return entries


def _llm_pick_assignee(task_desc: str, roster_entries: List[Dict[str, str]]) -> str:
    """Auxiliary LLM roster match. Seeded from kanban_decompose's LLM
    contract style; returns the raw picked name (caller validates)."""
    from agent.auxiliary_client import call_llm

    listing = "\n".join(
        f"- {e['name']}: {e['description']}" for e in roster_entries
    )
    resp = call_llm(
        task="kanban_specialist",
        messages=[
            {"role": "system", "content": _PICK_SYSTEM_PROMPT},
            {"role": "user", "content": f"Roster:\n{listing}\n\nTask: {task_desc}"},
        ],
        temperature=0,
        max_tokens=256,
        timeout=30,
    )
    return str(resp.choices[0].message.content or "").strip()


def route_task(task_desc: str, roster: Dict[str, Any]) -> Optional[str]:
    """Best-fit profile name for *task_desc*, or None when routing is
    disabled or has no roster. Fail-open: every error path returns the
    configured default_assignee (never None-with-routing-enabled, never a
    raise)."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config().get("kanban") or {}
        default = str(cfg.get("default_assignee") or "default")
        if not bool(cfg.get("specialist_routing", False)):
            return None
        entries = _roster_entries(roster)
        if not entries:
            return None
        known = {e["name"] for e in entries}
        try:
            picked = _llm_pick_assignee(task_desc, entries)
        except Exception as exc:
            logger.info("specialist routing: LLM pick failed (%s); "
                        "falling back to %s", exc, default)
            return default
        picked = picked.strip()
        if picked not in known:
            logger.info("specialist routing: picked unknown profile %r; "
                        "falling back to %s", picked, default)
            return default
        return picked
    except Exception as exc:
        logger.info("specialist routing: unavailable (%s); using default path", exc)
        return None
```

(premise: roster source — adapt `route_task`'s caller plumbing and the fixture to the REAL roster store found in premise check 1c; the helper above stays, the reader moves.)

- [ ] **Step 4: GREEN** — expect 5 passed.
- [ ] **Step 5: Commit** — `feat(kanban): specialist routing (opt-in, fail-open roster match)`

---

### Task 2: Learnings store + worker-prompt injection

**Files:**
- Modify: `hermes_cli/kanban_specialist.py` (learnings store)
- Modify: `hermes_cli/kanban_db_dispatch.py` (spawn-time injection)
- Modify: `hermes_cli/kanban.py` + `hermes_cli/kanban_parser.py` (`hermes kanban learn <assignee> <text>`)
- Test: `tests/hermes_cli/test_kanban_specialist.py`

- [ ] **Step 1: Failing tests**

```python
class TestLearnings:
    def test_write_and_read_learnings(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        ks.record_learning(str(home / "kanban"), "backend-dev",
                           "The API uses cursor pagination, not offsets.")
        text = ks.load_learnings(str(home / "kanban"), "backend-dev")
        assert "cursor pagination" in text

    def test_learnings_scoped_per_assignee(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        ks.record_learning(str(home / "kanban"), "backend-dev", "api note")
        ks.record_learning(str(home / "kanban"), "frontend-dev", "ui note")
        assert "api note" in ks.load_learnings(str(home / "kanban"), "backend-dev")
        assert "api note" not in ks.load_learnings(str(home / "kanban"), "frontend-dev")

    def test_learnings_append_with_timestamp(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        ks.record_learning(str(home / "kanban"), "backend-dev", "note one")
        ks.record_learning(str(home / "kanban"), "backend-dev", "note two")
        text = ks.load_learnings(str(home / "kanban"), "backend-dev")
        assert "note one" in text and "note two" in text

    def test_empty_learnings_returns_empty_string(self, board_env):
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        assert ks.load_learnings(str(home / "kanban"), "nobody") == ""

    def test_worker_prompt_includes_learnings(self, board_env, monkeypatch):
        """Spawn-time injection: the worker prompt built for assignee X
        contains X's learnings verbatim (after the task body)."""
        # premise check 1b: adapt to the real prompt-construction function —
        # the contract is: given (task_body, assignee), the built prompt
        # contains the learnings text. Implement against the real seam.
        from hermes_cli import kanban_specialist as ks

        home, _conn = board_env
        ks.record_learning(str(home / "kanban"), "backend-dev",
                           "Cursor pagination only.")
        prompt = ks.build_worker_prompt(
            task_body="Add pagination.", assignee="backend-dev",
        )
        assert "Cursor pagination only." in prompt
        assert "Add pagination." in prompt
        assert prompt.find("Add pagination.") < prompt.find("Cursor pagination only.")
```

- [ ] **Step 2: RED** — record.
- [ ] **Step 3: Implement** (learnings store + `build_worker_prompt(task_body, assignee)` helper + wire into the REAL spawn-prompt site found in premise check 1b; the injection must be conditional — empty learnings inject nothing, not even a header). CLI verb `hermes kanban learn <assignee> <text>` (kanban_parser.py subparser + kanban.py handler calling record_learning; required args, no confirm).
- [ ] **Step 4: GREEN** — expect 5 + 5 = 10 passed.
- [ ] **Step 5: Regression** — `scripts/run_tests.sh tests/hermes_cli/test_kanban_db.py tests/hermes_cli/test_kanban_promote.py tests/hermes_cli/test_kanban_swarm.py -j 3 -q`; record.
- [ ] **Step 6: Commit** — `feat(kanban): durable per-specialist learnings injected at spawn`

---

### Task 3: Dispatcher wiring + audit comment

**Files:**
- Modify: `hermes_cli/kanban_db_dispatch.py`
- Test: `tests/hermes_cli/test_kanban_specialist.py`

- [ ] **Step 1: Failing test** — the dispatch flow: a ready task with no assignee, under specialist_routing, gets picked → routed → a comment records the routing decision (audit) → falls back to default_assignee on any routing failure.

```python
class TestDispatcherWiring:
    def test_unassigned_ready_task_routed_and_audited(
        self, board_env, roster, monkeypatch
    ):
        """Integration through the real dispatch tick: unassigned ready task
        → routed to backend-dev → audit comment records the pick."""
        # premise: adapt to the real dispatch-tick entry (kanban_db_dispatch
        # run_dispatch_tick or equivalent) — construct a ready unassigned
        # task, patch ks.route_task to return "backend-dev", run one tick,
        # assert the task's assignee == "backend-dev" and a comment exists
        # containing "specialist route". Then a routing-failure variant
        # (route_task returns "default") asserts default_assignee + audit.
```

- [ ] **Step 2-4: RED → wire → GREEN** (the wiring must re-read the real dispatch code; the invariant: routing runs ONLY when the task would otherwise get default_assignee — explicit operator assignments are never overridden).
- [ ] **Step 5: Regression** — same kanban suites + `tests/hermes_cli/test_kanban_dispatch_tick_hook.py` if present.
- [ ] **Step 6: Commit** — `feat(kanban): dispatcher wiring for specialist routing + audit`

---

### Task 4: Config key + docs

**Files:**
- Modify: `hermes_cli/config.py` (DEFAULT_CONFIG `kanban.specialist_routing: false`)
- Modify: `website/docs/user-guide/features/kanban.md`

- [ ] **Step 1:** config key + `scripts/run_tests.sh tests/hermes_cli/test_config.py -j 1 -q` (record; pre-existing failures verified by stash A/B).
- [ ] **Step 2:** docs — "## Specialist routing and learnings": opt-in flag, roster source, fail-open contract, learnings lifecycle (`hermes kanban learn`), audit comments.
- [ ] **Step 3:** Commit — `docs+config: specialist workforce routing guide`

---

### Task 5: Final review

Full-range diff review against the governance contract (fail-open routing, roster honesty, read-only injection, no capacity/reclaim changes), all suite runs, follow-up list (pre-warming, auto-scaling, worker-driven learning writes — deliberately deferred).

Self-review note: `route_task` returns None when disabled (caller unchanged) vs default_assignee when enabled-but-failed — the two None-vs-default semantics are load-bearing for the dispatcher wiring; the implementer must keep them distinct and test both. The roster source premise check is the highest-risk adaptation in Task 1; if no JSON roster exists, the implementer defines the roster read from the real profile store and adapts the fixture to patch that reader — tests stay authoritative.

## Status: COMPLETE (2026-09-06)

Commits 7a50b7b926..289ddb7b5e. Final review verdict READY — 23/23
specialist suite, 4+16 worker_argv/promote, 229+1(pre-existing) kanban_db,
29/29 skill-evolution cross-sanity. Governance traced: hook inside
`if not row_assignee:` (explicit assignments structurally unreachable),
breaker attempted-flag (disabled never calls route_task; max 1 aux call/tick
under failure), learnings injection fail-open (base prompt on any error),
reasoning_effort upstream-verbatim restore unblocked real spawns (the
adoption had dropped the field — every spawn AttributeError'd).

MAJOR baseline repair surfaced by wiring: the module split had dropped ~14
late-bound helpers (_host_prefix, _env_int, _git_out, lifecycle-hook
plumbing, ...) — every dispatch tick AttributeError'd on the pristine tree.
Restored verbatim (verified against e03a680592^, 10 byte-identical).

Follow-ups (non-blocking): unfenced-ladder coverage matrix entry for the
kanban_specialist task; MoA guidance; per-tick time budget for successful
routings; _apply_default_assignee rowcount truthfulness; baseline-repair
queue (DispatchResult duplication, _wal_fallback_warned_paths,
request_review, observability module).
