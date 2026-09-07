# Autonomous Blocked-Outcome Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the governed objective runtime autonomously resolve blocked outcomes within charter policy — bounded replanning, then policy-driven abandonment — never reporting failure as success, never auto-acting on security/integrity/budget blockers, and preserving operator stop controls.

**Architecture:** Add a charter section (`agentic.blocked_outcome_policy`) validated in `objective_policy.validate_charter`; a durable per-objective attempt counter (idempotent `ALTER TABLE`); and a policy application layer in `ObjectiveRuntime._run_claimed_event`'s blocked paths that transitions `blocked → planned` (replan event with backoff) or `blocked → abandoned` (terminal, evidence recorded). Under `mode: "advise"` (default) behavior is byte-identical to today. Security/integrity/readiness/budget categories are hard-excluded from autonomous resolution. The policy runs only under autonomy_mode "autonomous" with a current generation, so `/stop` and master-stop always win.

**Tech Stack:** Python, SQLite (existing idempotent-migration pattern), pytest via `scripts/run_tests.sh`.

**Files:**
- Modify: `hermes_cli/objective_policy.py` (charter validation)
- Modify: `hermes_cli/objectives_db.py` (counter column + record helper)
- Modify: `hermes_cli/objective_runtime.py` (policy application at blocked paths)
- Create: `tests/hermes_cli/test_objective_blocked_outcome_policy.py`

---

### Task 1: Charter policy parsing and validation

**Files:**
- Modify: `hermes_cli/objective_policy.py`
- Test: `tests/hermes_cli/test_objective_blocked_outcome_policy.py`

- [ ] **Step 1: Write failing tests for the policy contract**

```python
"""Autonomous blocked-outcome policy: charter contract + runtime behavior.

The approved boundary: blocked work is durably deferred, replanned, or
abandoned per policy — never reported successful; security/integrity/budget
blockers always require human resolution; operator stops always win.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from hermes_cli import objective_policy


def _charter(**overrides):
    charter = {
        "enabled": True,
        "operating_mode": "autonomous",
        "max_autonomous_risk": "medium",
        "permit_ttl_seconds": 300,
        "runtime_host": "gateway",
        "blocked_outcome_policy": {
            "mode": "autonomous",
            "max_replan_attempts": 2,
            "replan_backoff_seconds": 60,
            "abandon_after_max": True,
        },
    }
    charter.update(overrides)
    return charter


class TestCharterValidation:
    def test_valid_autonomous_policy_accepted(self):
        objective_policy.validate_charter(_charter())  # must not raise

    def test_default_missing_policy_is_advise(self):
        # No blocked_outcome_policy key: valid; defaults to advise-only.
        objective_policy.validate_charter(
            {k: v for k, v in _charter().items() if k != "blocked_outcome_policy"}
        )

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValueError, match="blocked_outcome_policy.mode"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={"mode": "yolo"})
            )

    def test_nonpositive_attempts_rejected(self):
        with pytest.raises(ValueError, match="max_replan_attempts"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous", "max_replan_attempts": 0
                })
            )

    def test_negative_backoff_rejected(self):
        with pytest.raises(ValueError, match="replan_backoff_seconds"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous",
                    "max_replan_attempts": 1,
                    "replan_backoff_seconds": -5,
                })
            )

    def test_abandon_after_max_must_be_bool(self):
        with pytest.raises(ValueError, match="abandon_after_max"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous",
                    "max_replan_attempts": 1,
                    "abandon_after_max": "yes",
                })
            )
```

- [ ] **Step 2: Run tests — expect failures (no blocked_outcome_policy handling)**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: 4 failures (valid policy accepted fails because unknown keys are fine but our new validators don't exist; the three invalid-input tests pass vacuously today — after Step 3 all must fail for the right reason. Record actual counts.)

- [ ] **Step 3: Implement validation in `objective_policy.validate_charter`**

Insert at the end of `validate_charter`, before the final `resource_limits` cross-check (or immediately after the `action_approvals` block):

```python
    policy = charter.get("blocked_outcome_policy")
    if policy is not None:
        if not isinstance(policy, Mapping):
            raise ValueError("agentic.blocked_outcome_policy must be a mapping")
        mode = str(policy.get("mode", "advise")).strip()
        if mode not in {"advise", "autonomous"}:
            raise ValueError(
                "agentic.blocked_outcome_policy.mode must be advise or autonomous"
            )
        if mode == "autonomous":
            attempts = policy.get("max_replan_attempts", 3)
            if not isinstance(attempts, int) or attempts <= 0 or attempts > 25:
                raise ValueError(
                    "agentic.blocked_outcome_policy.max_replan_attempts must be "
                    "a positive integer of at most 25"
                )
            backoff = policy.get("replan_backoff_seconds", 60)
            if not isinstance(backoff, int) or backoff < 0:
                raise ValueError(
                    "agentic.blocked_outcome_policy.replan_backoff_seconds must "
                    "be a non-negative integer"
                )
            abandon = policy.get("abandon_after_max", True)
            if not isinstance(abandon, bool):
                raise ValueError(
                    "agentic.blocked_outcome_policy.abandon_after_max must be a "
                    "boolean"
                )
```

- [ ] **Step 4: Run tests — expect all 6 passing**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add hermes_cli/objective_policy.py tests/hermes_cli/test_objective_blocked_outcome_policy.py
git commit -m "feat(agentic): charter blocked_outcome_policy validation"
```

---

### Task 2: Durable per-objective replan counter

**Files:**
- Modify: `hermes_cli/objectives_db.py` (column + helpers)
- Test: `tests/hermes_cli/test_objective_blocked_outcome_policy.py`

- [ ] **Step 1: Write failing tests for the counter helpers**

Append to the test file:

```python
@pytest.fixture()
def conn():
    from hermes_cli import objectives_db

    conn = objectives_db.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _make_objective(conn, *, originator="human_operator:setup"):
    from hermes_cli import objectives_db as db

    return db.create_objective(
        conn,
        organization_id="__unscoped__",
        desired_outcome="prove the outcome",
        originator=originator,
        owner=f"employee:ceo-1",
        constraints=[],
        authority_scope={"capabilities": []},
        success_criteria=[{"verifier": "v", "params": {}}],
        termination_conditions=[],
        permitted_systems=[],
        prohibited_actions=[],
        max_spend_minor=1000,
        currency="USD",
        expires_at=None,
    )


class TestReplanCounter:
    def test_column_exists_and_defaults_zero(self, conn):
        row = conn.execute(
            "SELECT blocked_replan_attempts FROM objectives LIMIT 1"
        ).fetchone()
        # Fresh schema has the column; zero rows is also fine.
        if row is not None:
            assert row["blocked_replan_attempts"] == 0

    def test_increment_and_reset(self, conn):
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        assert db.record_blocked_replan(conn, obj.id) == 1
        assert db.record_blocked_replan(conn, obj.id) == 2
        db.reset_blocked_replan(conn, obj.id)
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_counter_is_scoped_per_objective(self, conn):
        from hermes_cli import objectives_db as db

        a = _make_objective(conn)
        b = _make_objective(conn)
        db.record_blocked_replan(conn, a.id)
        assert db.blocked_replan_attempts(conn, b.id) == 0

    def test_reset_on_terminal_transition(self, conn):
        """Abandon/cancel/expiry must reset the counter (fresh attempts if the
        objective is ever re-proposed under a new id)."""
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        db.record_blocked_replan(conn, obj.id)
        db.transition_objective(conn, obj.id, "abandoned", actor="test")
        assert db.blocked_replan_attempts(conn, obj.id) == 0
```

- [ ] **Step 2: Run — expect failures (no such helpers/column)**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: counter tests fail with AttributeError/OperationalError.

- [ ] **Step 3: Implement in `objectives_db.py`**

In the schema/bootstrap function that runs the idempotent `ALTER TABLE` block (after the `organization_id` migration, near line 545):

```python
    if "blocked_replan_attempts" not in columns:
        conn.execute(
            "ALTER TABLE objectives ADD COLUMN "
            "blocked_replan_attempts INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
```

Add to `SCHEMA_SQL`'s `objectives` table definition (before `reaffirmed_at INTEGER NOT NULL,`):

```sql
    blocked_replan_attempts INTEGER NOT NULL DEFAULT 0,
```

Add module-level helpers (near `transition_objective`):

```python
def blocked_replan_attempts(conn: sqlite3.Connection, objective_id: str) -> int:
    row = conn.execute(
        "SELECT blocked_replan_attempts FROM objectives WHERE id=?",
        (objective_id,),
    ).fetchone()
    return int(row["blocked_replan_attempts"] or 0) if row is not None else 0


def record_blocked_replan(conn: sqlite3.Connection, objective_id: str) -> int:
    """Increment and return the durable blocked-replan attempt counter."""
    with conn:
        conn.execute(
            "UPDATE objectives SET blocked_replan_attempts = "
            "blocked_replan_attempts + 1, updated_at = ? WHERE id=?",
            (_now(), objective_id),
        )
    return blocked_replan_attempts(conn, objective_id)


def reset_blocked_replan(conn: sqlite3.Connection, objective_id: str) -> None:
    with conn:
        conn.execute(
            "UPDATE objectives SET blocked_replan_attempts = 0, updated_at = ? "
            "WHERE id=?",
            (_now(), objective_id),
        )
```

Check `transition_objective`: if it records an updated_at already, add counter reset there for terminal statuses (`abandoned`, `cancelled`, `expired`, `superseded`, `closed`) — implement inside `transition_objective` after the status write:

```python
    if next_status in TERMINAL_OBJECTIVE_STATUSES:
        reset_blocked_replan(conn, objective_id)
```

(`TERMINAL_OBJECTIVE_STATUSES` already exists in this module.)

- [ ] **Step 4: Run — expect all counter tests green; prior charter tests still green**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: 10 passed.

- [ ] **Step 5: Run existing objectives_db suite for migration regressions**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objectives_db.py -j 1 -q`
Expected: all pass (no regression from the new column).

- [ ] **Step 6: Commit**

```bash
git add hermes_cli/objectives_db.py tests/hermes_cli/test_objective_blocked_outcome_policy.py
git commit -m "feat(agentic): durable per-objective blocked-replan counter"
```

---

### Task 3: Policy application at blocked paths

**Files:**
- Modify: `hermes_cli/objective_runtime.py`
- Test: `tests/hermes_cli/test_objective_blocked_outcome_policy.py`

- [ ] **Step 1: Write failing runtime tests**

Append to the test file:

```python
class _StubPlanner:
    identity = "stub-planner"

    def propose(self, snapshot, event):
        raise AssertionError("planner should not be reached in these tests")


class _StubExecutor:
    identity = "stub-executor"

    def execute(self, action, context):  # pragma: no cover
        raise AssertionError("no execution expected")


class _StubVerifier:
    identity = "stub-verifier"

    def verify(self, action, result):  # pragma: no cover
        raise AssertionError("no action verification expected")

    def verify_objective(self, snapshot, proposal, results):
        from hermes_cli.objective_runtime import VerificationOutcome

        return VerificationOutcome("fail", "evidence insufficient")


@pytest.fixture()
def runtime_env(mocker, conn):
    """ObjectiveRuntime with stubbed planner/executor/verifier and a charter."""
    from hermes_cli.objective_runtime import ObjectiveRuntime

    charter = _charter()
    rt = ObjectiveRuntime(
        conn,
        charter=charter,
        planner=_StubPlanner(),
        executor=_StubExecutor(),
        verifier=_StubVerifier(),
        policy_version="test-v1",
    )
    return rt


def _enqueue_event(conn, objective_id, event_type="ceo.operating_review"):
    from hermes_cli import objectives_db as db

    return db.enqueue_objective_event(
        conn,
        objective_id=objective_id,
        event_type=event_type,
        payload={"source": "test"},
    )


def _claim_and_tick(rt, conn, objective_id):
    event = conn.execute(
        "SELECT * FROM objective_inbox WHERE objective_id=? AND "
        "status='pending' ORDER BY created_at LIMIT 1",
        (objective_id,),
    ).fetchone()
    from hermes_cli import objectives_db as db

    claimed = db.claim_objective_event(conn, runtime_id="test-runtime")
    assert claimed is not None
    rt.conn = conn
    return rt._run_claimed_event(claimed)


class TestAutonomousReplan:
    def test_no_admissible_action_replans_within_budget(self, runtime_env, conn, monkeypatch):
        """First blocked outcome: policy replans (durable event + counter=1),
        objective stays non-terminal, NO open intervention is raised."""
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        db.transition_objective(conn, obj.id, "accepted", actor="test")
        _enqueue_event(conn, obj.id)

        rt = runtime_env
        outcome = _claim_and_tick(rt, conn, obj.id)

        # The planner proposes no actions -> today: blocked + advisor handoff.
        # Under policy: replan scheduled, counter incremented.
        assert db.blocked_replan_attempts(conn, obj.id) == 1
        current = db.get_objective(conn, obj.id)
        assert current.status in {"planned", "blocked"}
        replans = conn.execute(
            "SELECT * FROM objective_inbox WHERE objective_id=? AND "
            "event_type='objective.replan' AND status='pending'",
            (obj.id,),
        ).fetchall()
        assert len(replans) == 1
        # No demanding intervention for this category under autonomous policy.
        from hermes_cli import operational_control

        open_interventions = conn.execute(
            "SELECT * FROM intervention_queue WHERE objective_id=? AND "
            "status='open' AND category='no_admissible_action'",
            (obj.id,),
        ).fetchall()
        assert open_interventions == []

    def test_attempts_exhausted_abandons_objective(self, runtime_env, conn):
        """At max_replan_attempts the objective transitions to abandoned —
        NEVER completed or verified."""
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        db.transition_objective(conn, obj.id, "accepted", actor="test")
        _enqueue_event(conn, obj.id)
        rt = runtime_env
        # Burn the two allowed replans.
        db.record_blocked_replan(conn, obj.id)
        db.record_blocked_replan(conn, obj.id)
        outcome = _claim_and_tick(rt, conn, obj.id)
        current = db.get_objective(conn, obj.id)
        assert current.status == "abandoned"
        # Terminal + counter reset (Task 2 behavior).
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_budget_category_never_autonomously_resolved(self, runtime_env, conn, monkeypatch):
        """resource_budget_exhausted is hard-excluded: it always demands human
        resolution even under autonomous policy."""
        from hermes_cli import objectives_db as db
        from hermes_cli import resource_budget

        obj = _make_objective(conn)
        db.transition_objective(conn, obj.id, "accepted", actor="test")
        _enqueue_event(conn, obj.id)

        def explode(*a, **k):
            raise resource_budget.ResourceBudgetError("objective budget exhausted")

        monkeypatch.setattr(resource_budget, "assert_admissible", explode)
        outcome = _claim_and_tick(rt=runtime_env, conn=conn, objective_id=obj.id)
        from hermes_cli import objectives_db as db

        current = db.get_objective(conn, obj.id)
        assert current.status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0
        from hermes_cli import operational_control

        open_iv = conn.execute(
            "SELECT * FROM intervention_queue WHERE objective_id=? AND "
            "category='resource_budget_exhausted' AND status='open'",
            (obj.id,),
        ).fetchall()
        assert len(open_iv) == 1

    def test_advise_mode_is_byte_identical_to_legacy(self, conn):
        """mode="advise" (default): the advisor handoff fires exactly as
        before, no replan event, no counter change."""
        from hermes_cli.objective_runtime import ObjectiveRuntime
        from hermes_cli import objectives_db as db

        charter = _charter(blocked_outcome_policy={
            "mode": "advise", "max_replan_attempts": 3
        })
        rt = ObjectiveRuntime(
            conn, charter=charter, planner=_StubPlanner(),
            executor=_StubExecutor(), verifier=_StubVerifier(),
            policy_version="test-v1",
        )
        obj = _make_objective(conn)
        db.transition_objective(conn, obj.id, "accepted", actor="test")
        _enqueue_event(conn, obj.id)
        _claim_and_tick(rt, conn, obj.id)

        current = db.get_objective(conn, obj.id)
        assert current.status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0
        replans = conn.execute(
            "SELECT * FROM objective_inbox WHERE objective_id=? AND "
            "event_type='objective.replan'",
            (obj.id,),
        ).fetchall()
        assert replans == []

    def test_operator_stop_wins_over_policy(self, runtime_env, conn, monkeypatch):
        """Autonomy mode paused/revoked (generation bumped) must prevent
        autonomous replanning even with an autonomous charter policy."""
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        db.transition_objective(conn, obj.id, "accepted", actor="test")
        _enqueue_event(conn, obj.id)
        rt = runtime_env
        # Simulate the operator stopping autonomy: charter's operating_mode
        # flipped mid-flight is the durable evidence the runtime re-reads.
        rt.charter = dict(rt.charter)
        rt.charter["operating_mode"] = "supervised"
        outcome = _claim_and_tick(rt, conn, obj.id)
        from hermes_cli import objectives_db as db

        assert db.get_objective(conn, obj.id).status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0
```

Note on the `_StubPlanner`: `propose` raising AssertionError means "no admissible action" is NOT exercised — instead the planner must return a `PlanProposal` with empty actions. Correct the stub:

```python
class _StubPlanner:
    identity = "stub-planner"

    def propose(self, snapshot, event):
        from hermes_cli.objective_runtime import PlanProposal

        return PlanProposal(assumptions=[], tasks=["await guidance"],
                            dependencies=[], risks=[],
                            actions=[], objective_complete_when_verified=False)
```

(Use THIS stub in the fixture; the AssertionError variant above is wrong — with it the runtime records a planner exception, not a no-action block. Record actual behavior and adjust assertions to the real CycleOutcome.)

- [ ] **Step 2: Run — expect failures (policy not applied)**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: new runtime tests fail (counter stays 0 / interventions raised / abandonment doesn't happen).

- [ ] **Step 3: Implement in `objective_runtime.py`**

Add a helper method on `ObjectiveRuntime` (near `_raise_advisor_handoff`, line ~392):

```python
    # Blocked categories that are NEVER autonomously resolvable. Any change
    # here is a governance decision, not a tuning knob: these demand human
    # resolution by design (security posture, authority integrity, spend).
    _HUMAN_ONLY_BLOCKED_CATEGORIES = frozenset({
        "resource_budget_exhausted",
        "planner_contract_violation",
        "executor_authority_rejected",
        "security_readiness_blocked",
        "integrity_blocked",
    })

    def _resolve_blocked_outcome(
        self,
        *,
        event_id: str,
        objective_id: str,
        category: str,
        reason: str,
        context: Mapping[str, Any],
        options: list,
    ) -> CycleOutcome:
        """Apply the charter's blocked_outcome_policy to one blocked outcome.

        advise (default): raise the advisor handoff, leave the objective
        blocked — identical to the pre-policy behavior.

        autonomous: for replannable categories, record a durable objective.
        replan event with backoff and transition the objective back to
        "planned" so the next cycle re-plans with the blocked evidence in its
        snapshot. When the attempt budget is exhausted: abandon (terminal,
        evidence preserved) — never "completed"/"verified".

        Human-only categories always fall back to the advisor handoff
        regardless of policy mode.
        """
        from hermes_cli import objective_policy as _policy

        policy = (self.charter.get("blocked_outcome_policy") or {})
        mode = str(policy.get("mode", "advise"))
        if (
            mode != "autonomous"
            or category in self._HUMAN_ONLY_BLOCKED_CATEGORIES
            or str(self.charter.get("operating_mode", "")) != "autonomous"
        ):
            self._raise_advisor_handoff(
                objective_id=objective_id,
                category=category,
                summary=reason,
                context=context,
                options=options,
            )
            if db.get_objective(self.conn, objective_id).status != "blocked":
                db.transition_objective(
                    self.conn, objective_id, "blocked",
                    actor=self.runtime_id, reason=reason,
                )
            return CycleOutcome(event_id, objective_id, "blocked", reason)

        attempts = db.record_blocked_replan(self.conn, objective_id)
        max_attempts = int(policy.get("max_replan_attempts", 3))
        backoff = int(policy.get("replan_backoff_seconds", 60))
        if attempts < max_attempts:
            db.enqueue_objective_event(
                self.conn,
                objective_id=objective_id,
                event_type="objective.replan",
                payload={"category": category, "reason": reason,
                         "attempt": attempts},
                available_at=int(time.time()) + backoff,
                dedupe_key=f"replan:{objective_id}:{attempts}",
            )
            db.transition_objective(
                self.conn, objective_id, "planned",
                actor=self.runtime_id,
                reason=f"autonomous replan {attempts}/{max_attempts}: {reason}",
            )
            business_audit.append(
                self.conn,
                organization_id=(
                    db.get_objective(self.conn, objective_id).organization_id
                ),
                event_type="objective.autonomous_replan",
                objective_id=objective_id,
                payload={"attempt": attempts, "max": max_attempts,
                         "category": category, "reason": reason},
            )
            return CycleOutcome(event_id, objective_id, "replan_scheduled", reason)
        # Budget exhausted: policy-driven abandonment (terminal; the counter
        # resets on the terminal transition).
        if bool(policy.get("abandon_after_max", True)):
            db.transition_objective(
                self.conn, objective_id, "abandoned",
                actor=self.runtime_id,
                reason=f"replan budget exhausted after {attempts} attempts: {reason}",
            )
            business_audit.append(
                self.conn,
                organization_id=(
                    db.get_objective(self.conn, objective_id).organization_id
                ),
                event_type="objective.autonomous_abandon",
                objective_id=objective_id,
                payload={"attempts": attempts, "category": category,
                         "reason": reason},
            )
            return CycleOutcome(event_id, objective_id, "abandoned", reason)
        # abandon_after_max disabled: stay blocked and demand human input.
        self._raise_advisor_handoff(
            objective_id=objective_id,
            category=category,
            summary=reason,
            context={**context, "replan_attempts": attempts},
            options=options,
        )
        if db.get_objective(self.conn, objective_id).status != "blocked":
            db.transition_objective(
                self.conn, objective_id, "blocked",
                actor=self.runtime_id, reason=reason,
            )
        return CycleOutcome(event_id, objective_id, "blocked", reason)
```

Check imports present in the module: `time`, `Mapping` (typing), `business_audit`, `db` — all already imported at module level (verify; add `from hermes_cli import business_audit` if absent).

Then replace the THREE blocked-path sites in `_run_claimed_event` to route through the helper:

1. **`objective_evidence_insufficient`** (~line 1456): keep the `verification_id` recording, then replace
   ```python
   self._raise_advisor_handoff(objective_id=..., category="objective_evidence_insufficient", ...)
   db.transition_objective(self.conn, objective_id, "blocked", ...)
   return CycleOutcome(str(event["id"]), objective_id, "blocked", ...)
   ```
   with
   ```python
   return self._resolve_blocked_outcome(
       event_id=str(event["id"]),
       objective_id=objective_id,
       category="objective_evidence_insufficient",
       reason=f"objective verification {objective_verification.verdict}",
       context={"plan_id": plan_id, "verification_id": verification_id,
                "verdict": objective_verification.verdict},
       options=[
           {"id": "collect_evidence", "label": "Collect stronger evidence"},
           {"id": "replan", "label": "Replan toward the success criteria"},
           {"id": "abandon", "label": "Abandon the objective"},
       ],
   )
   ```

2. **`no_admissible_action`** (~line 1497): same replacement pattern — keep the advisor options, replace the raise+transition+return with `return self._resolve_blocked_outcome(... category="no_admissible_action" ...)`.

3. **`planner_contract_violation`** and **`executor_authority_rejected`** (~line 1366/1400): these are human-only; leave their existing raise paths UNCHANGED (do not route through the helper — they hard-fail to the advisor by design). Only the two replannable categories route through the helper.

Also extend `_resolve_blocked_outcome`'s advisor options in the exhausted case with the actual attempts evidence (the helper already does via `replan_attempts`).

- [ ] **Step 4: Run — expect the runtime tests green**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: all tests pass (adjust the fixture stub per the Note; record actual CycleOutcome statuses and align assertions — the *contract* is counter/replan/abandon/non-terminal, not the exact status string).

- [ ] **Step 5: Regression run of the whole objective family**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_service.py tests/hermes_cli/test_objective_worker.py tests/hermes_cli/test_objective_runtime*.py tests/hermes_cli/test_objective_policy*.py -j 4 -q`
Expected: no regressions (advise-mode default means existing tests are unaffected).

- [ ] **Step 6: Commit**

```bash
git add hermes_cli/objective_runtime.py tests/hermes_cli/test_objective_blocked_outcome_policy.py
git commit -m "feat(agentic): autonomous blocked-outcome policy (bounded replan + abandon)"
```

---

### Task 4: Restart durability of the replan loop

**Files:**
- Test: `tests/hermes_cli/test_objective_blocked_outcome_policy.py`

- [ ] **Step 1: Write the durability test**

```python
def test_replan_survives_restart(runtime_env, conn):
    """The scheduled replan event is durable: a fresh runtime instance on the
    same store picks it up and continues the attempt sequence — the counter
    and pending event survive process death."""
    from hermes_cli.objective_runtime import ObjectiveRuntime
    from hermes_cli import objectives_db as db

    obj = _make_objective(conn)
    db.transition_objective(conn, obj.id, "accepted", actor="test")
    _enqueue_event(conn, obj.id)
    _claim_and_tick(runtime_env, conn, obj.id)  # first block -> replan scheduled

    # Simulate restart: zero out the replan event's backoff so it's due now,
    # then run a NEW runtime instance on the same connection.
    conn.execute(
        "UPDATE objective_inbox SET available_at = 0 "
        "WHERE event_type='objective.replan'"
    )
    conn.commit()
    rt2 = ObjectiveRuntime(
        conn, charter=_charter(), planner=_StubPlanner(),
        executor=_StubExecutor(), verifier=_StubVerifier(),
        policy_version="test-v1",
    )
    outcome2 = _claim_and_tick(rt2, conn, obj.id)

    assert db.blocked_replan_attempts(conn, obj.id) == 2
    replans = conn.execute(
        "SELECT COUNT(*) AS n FROM objective_inbox WHERE objective_id=? AND "
        "event_type='objective.replan'",
        (obj.id,),
    ).fetchone()
    assert replans["n"] == 2
```

- [ ] **Step 2: Run — expect pass (durable by construction via the inbox table; if it fails, fix the backoff requeue to use the DB, not runtime memory)**

Run: `scripts/run_tests.sh tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 1 -q`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add tests/hermes_cli/test_objective_blocked_outcome_policy.py
git commit -m "test(agentic): replan loop survives restart via durable inbox"
```

---

### Task 5: Setup wizard exposure + docs

**Files:**
- Modify: `hermes_cli/setup.py` (agentic charter prompt)
- Modify: `website/docs/guides/agentic-business-os.md`

- [ ] **Step 1: Add the policy question to `setup_agentic_settings`** — after the operating-cadence block, prompt (curses fallback to input): "When an objective gets stuck, how should the business respond?" options: advise (default) / autonomous replan with N attempts (default 3). Store into `config["agentic"]["blocked_outcome_policy"]`.

- [ ] **Step 2: Run the agentic setup tests**

Run: `scripts/run_tests.sh tests/hermes_cli/test_setup_agentic.py -j 1 -q`
Expected: pass (new prompt defaults must not break existing fixtures).

- [ ] **Step 3: Document the policy in the guide** — one section: defaults, guardrails (human-only categories, stop-control precedence), and how to set it.

- [ ] **Step 4: Commit**

```bash
git add hermes_cli/setup.py website/docs/guides/agentic-business-os.md
git commit -m "docs+setup: expose blocked_outcome_policy in agentic charter"
```
