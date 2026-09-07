# State Import Recovery Implementation Plan

> **For agentic workers:** Use the executing-plans skill. Steps use checkbox syntax.

**Goal:** Restore SessionDB imports by adding the missing `_PREVIEW_RAW_SUBQUERY_SQL` correlated-preview constant to `hermes_state_common.py`, extracted verbatim from upstream — no fabricated alias.

**Architecture:** The untracked `hermes_state_portability.py` mixin interpolates the constant as a SELECT-list expression in `_rich_select` (`_PREVIEW_RAW_SUBQUERY_SQL,` at column position 2). The reference semantics live inline in `hermes_state.py:11889-11897`: correlated subquery over `messages m` filtered to the session row, user role, non-null content, `_PREVIEW_ELIGIBLE_SQL`; ordered `m.timestamp, m.id LIMIT 1`; wrapped `COALESCE(..., '')`; aliased `_preview_raw`. Upstream `hermes_state_common.py:106-108` defines exactly this — extract it.

**Tech Stack:** Python, SQLite, canonical `scripts/run_tests.sh`.

## Authority And Scope

Same approved boundary: unattended operation within configured authority; operator stops authoritative. This gate repairs imports only — no behavior change, no schema change, no runtime enabling. Untracked sources (`hermes_state_portability.py`, `agent/session_activity.py`, `hermes_startup_watchdog.py`) stay untracked and byte-preserved; this patch edits only the tracked `hermes_state_common.py` plus one new test.

## Premise Validation (done during investigation)

- `python3 -c "import hermes_state"` → `ImportError: cannot import name '_PREVIEW_RAW_SUBQUERY_SQL' from 'hermes_state_common'` (the two provider-plugin warnings are separate documented findings).
- AST scan of the mixin's `Name` nodes referencing common symbols: `SCHEMA_SQL`, `_PREVIEW_RAW_SUBQUERY_SQL`, `_shape_preview`, `_sql_session_last_active` — only `_PREVIEW_RAW_SUBQUERY_SQL` missing.
- `_PREVIEW_RAW_SELECT` (CASE body over alias `m`) and `_PREVIEW_ELIGIBLE_SQL` (fork `hermes_state_common.py:133,147`) both exist and match the subquery's needs.
- `SKILL_SCAFFOLD_SQL_LIKE` (`agent/skill_commands.py:64`), `safe_json_loads` (`utils.py:407`) — present.
- Upstream extraction verified: `git show upstream/main:hermes_state_common.py` lines 106-108.

## Task 1: Red Test

- [ ] Add to `tests/hermes_state/test_portability_import_contract.py` (new file):

```python
"""Pin the _PREVIEW_RAW_SUBQUERY_SQL contract hermes_state_portability._rich_select depends on.

hermes_state_common must export the correlated preview subquery as a
SELECT-list expression (not a bare CASE body): correlated on s.id, user-role,
eligible content, timestamp/id ordering, COALESCE-fallback, _preview_raw alias.
"""
from __future__ import annotations

import hermes_state_common as hc


def test_preview_raw_subquery_exists_and_is_correlated():
    sql = hc._PREVIEW_RAW_SUBQUERY_SQL
    assert "m.session_id = s.id" in sql
    assert "m.role = 'user'" in sql
    assert "m.content IS NOT NULL" in sql
    assert hc._PREVIEW_ELIGIBLE_SQL in sql
    assert "ORDER BY m.timestamp, m.id LIMIT 1" in sql
    assert "COALESCE(" in sql
    assert "AS _preview_raw" in sql


def test_rich_select_interpolates_subquery():
    from hermes_state_portability import _rich_select

    rendered = _rich_select("s.id, s.title", "1=1")
    assert hc._PREVIEW_RAW_SUBQUERY_SQL in rendered
    assert "_sql_session_last_active" not in rendered or rendered.count("last_active") == 1
```

- [ ] Red check: `scripts/run_tests.sh tests/hermes_state/test_portability_import_contract.py -j 1 -q` → collection error (`ImportError: cannot import name '_PREVIEW_RAW_SUBQUERY_SQL'`) — this is the intended red.

## Task 2: Minimal Repair

- [ ] Add to `hermes_state_common.py` immediately after the `_PREVIEW_RAW_SELECT` definition (verbatim upstream lines 106-108):

```python
# Correlated ``_preview_raw`` column for a ``sessions s`` row.
_PREVIEW_RAW_SUBQUERY_SQL = (f"COALESCE((SELECT {_PREVIEW_RAW_SELECT} FROM messages m"
    f" WHERE m.session_id = s.id AND m.role = 'user' AND m.content IS NOT NULL AND {_PREVIEW_ELIGIBLE_SQL}"
    f" ORDER BY m.timestamp, m.id LIMIT 1), '') AS _preview_raw")
```

- [ ] Green check: repeat Task 1 command → 2 passed.

## Task 3: Exit Evidence

- [ ] `scripts/run_tests.sh tests/test_hermes_state.py -j 1 -q` → collection succeeds; record pass/fail counts. Failures inside the suite that relate to other known gates (dotenv, startup watchdog) are reported as separate blockers, not absorbed.
- [ ] `python3 -c "import hermes_state; from hermes_state_portability import SessionPortabilityMixin; print('imports OK')"` through the canonical environment.
- [ ] `git status --short` → only `hermes_state_common.py` + the new test modified/added; the three untracked files untouched.
- [ ] Stop: no commit until this gate is reviewed; no runtime enabling.

## Task 4: Full State-Layer Restoration (adopt upstream's 21-module refactor)

**Premise validated (investigation, 2026-09-06):**
- Fork `hermes_state.py` = 16,850-line hybrid (pre-refactor monolith + 5 submodule imports grafted).
- Upstream = 1,370-line thin coordinator over 21 modules. Diff: +16,575/-1,094.
- The only fork commits ever touching `hermes_state.py` are the three cherry-picked upstream fixes — zero fork/business-OS IP in this file. The -1,094 is pre-refactor residue.
- No fork-authored file (objective_*, organization_db, finance_db, accounting_db, compliance_db) references SessionDB.
- Fork callers import `get_shared_session_db`/`release_shared_session_db`/`close_shared_session_dbs` from `hermes_state`; upstream's coordinator doesn't re-export them but upstream `hermes_state_registry.py:232-238` defines all three. Fork's hybrid already re-exports them at line 4542.
- Red evidence: state suite 51 failed / 206 passed (e.g. `AttributeError: no attribute '_freelist_ratio'` — helper lives in upstream `hermes_state_maintenance`).

- [ ] Copy upstream's 21 state modules over the fork's partial set (`common, schema, search, registry` overwritten; `portability` untracked file removed, replaced by upstream's tracked version; 16 new modules added): compression, dbfile, errors, fts, gateway, guard, holders, maintenance, messages, readpool, repair, sessions, telegram, titles, usage, wal.
- [ ] Append to the adopted `hermes_state.py` (back-compat re-export, same symbols as fork line 4542 — real module, real functions):

```python
from hermes_state_registry import (  # noqa: F401  (re-export)
    close_shared_session_dbs,
    get_shared_session_db,
    release_or_close,
    release_shared_session_db,
)
```

- [ ] Green target: import check; `scripts/run_tests.sh tests/hermes_state/test_portability_import_contract.py -j 1 -q` → 2 passed; `scripts/run_tests.sh tests/test_hermes_state.py -j 1 -q` → 51 failures resolved or each remaining failure attributed to a distinct documented gate (dotenv, startup watchdog, provider plugins).
- [ ] Downstream gates: `tests/hermes_cli/test_kanban_worktree_isolation.py`, `tests/security/test_gitspawn_config_injection.py`.
- [ ] `git status --short`: exactly 21 tracked state modules + adopted coordinator; untracked set reduced by one (`hermes_state_portability.py` now tracked-upstream). Commit this gate separately.

## Gate 2 Status: COMPLETE (2026-09-06, commit fb2ddf6692)

Adopted upstream's Sep-2026 module decomposition wholesale (292 missing modules +
~20 lagging monolith targets + auth family + compat machinery), with targeted
extractions preserving fork IP (config business-OS, setup agentic bootstrap —
recovered from 7863586008 after an earlier --theirs loss, goals fingerprint,
hermes_constants, curses_ui branding).

Exit evidence: tests/test_hermes_state.py 259/259; GHSA security 16/16; goals
101/101; kanban worktree 5/5; coding_context 55/55; portability contract 2/2.

Follow-on gates identified during this gate:
| Gate | Finding |
| --- | --- |
| Browser-layer decomposition | tools.browser_tool monolith (fork governed-browser IP, 3 commits) lacks 17 names the adopted browser_tool_* siblings import (AGENT_BROWSER_NPX_SPEC, orphan-reap registry, vision fallback). 2 console-window test failures remain. |
| Branding consistency | Upstream-adopted files carry "Hermes" user-facing strings (auth family 49+); fork rebrand strings lost in wholesale adoption. Cosmetic; needs a deliberate pass distinguishing protocol/model "Hermes" mentions from product branding. |
| Gateway startup verification | gateway/startup_watchdog.py arrived via adoption; verify gateway import chain + objective watcher wiring (gate 3). |
