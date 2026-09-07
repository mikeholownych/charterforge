"""Autonomous blocked-outcome policy: charter contract + runtime behavior.

This module pins the charter contract; runtime application tests are added by later tasks in the same plan.
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

    def test_attempts_upper_bound_pinned(self):
        objective_policy.validate_charter(
            _charter(blocked_outcome_policy={
                "mode": "autonomous", "max_replan_attempts": 25
            })
        )
        with pytest.raises(ValueError, match="max_replan_attempts"):
            objective_policy.validate_charter(
                _charter(blocked_outcome_policy={
                    "mode": "autonomous", "max_replan_attempts": 26
                })
            )

    def test_non_int_attempts_rejected(self):
        for bad in ("3", 2.5):
            with pytest.raises(ValueError, match="max_replan_attempts"):
                objective_policy.validate_charter(
                    _charter(blocked_outcome_policy={
                        "mode": "autonomous", "max_replan_attempts": bad
                    })
                )

    def test_non_int_backoff_rejected(self):
        for bad in ("60", 45.5, [10]):
            with pytest.raises(ValueError, match="replan_backoff_seconds"):
                objective_policy.validate_charter(
                    _charter(blocked_outcome_policy={
                        "mode": "autonomous",
                        "max_replan_attempts": 1,
                        "replan_backoff_seconds": bad,
                    })
                )

    def test_mode_whitespace_is_coerced(self):
        objective_policy.validate_charter(
            _charter(blocked_outcome_policy={"mode": "  autonomous  "})
        )


# Adaptation vs. the planned fixture: objectives_db.connect() resolves its
# path arg (":memory:" would become a literal <cwd>/:memory: file), so the
# store is opened against a per-test tmp_path instead. operational_control's
# schema is ensured up front so tests that legitimately raise no intervention
# (autonomous replan) can still assert on the empty intervention_queue table.
@pytest.fixture()
def conn(tmp_path):
    from hermes_cli import objectives_db
    from hermes_cli import operational_control

    conn = objectives_db.connect(tmp_path / "objectives.db")
    conn.row_factory = sqlite3.Row
    operational_control.ensure_schema(conn)
    return conn


def _make_objective(conn):
    from hermes_cli import objectives_db as db

    return db.create_objective(
        conn,
        organization_id="__unscoped__",
        desired_outcome="prove the outcome",
        originator="human_operator:setup",
        owner="employee:ceo-1",
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
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_increment_and_reset(self, conn):
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        assert db.record_blocked_replan(conn, obj.id) == 1
        assert db.record_blocked_replan(conn, obj.id) == 2
        with conn:
            db.reset_blocked_replan(conn, obj.id)
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_counter_is_scoped_per_objective(self, conn):
        from hermes_cli import objectives_db as db

        a = _make_objective(conn)
        b = _make_objective(conn)
        db.record_blocked_replan(conn, a.id)
        assert db.blocked_replan_attempts(conn, b.id) == 0

    # Adaptation vs. the planned test: "abandoned" is not reachable from the
    # "proposed" state (_TRANSITIONS); "cancelled" is reachable and terminal.
    def test_reset_on_terminal_transition(self, conn):
        from hermes_cli import objectives_db as db

        obj = _make_objective(conn)
        db.record_blocked_replan(conn, obj.id)
        db.transition_objective(conn, obj.id, "cancelled", actor="test")
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_record_raises_for_unknown_objective(self, conn):
        from hermes_cli import objectives_db as db

        with pytest.raises(KeyError, match="objective not found"):
            db.record_blocked_replan(conn, "obj-does-not-exist")

    def test_counter_survives_reopen(self, tmp_path):
        """Durability: the counter and the terminal-reset survive closing and
        reopening the store."""
        from hermes_cli import objectives_db as db

        path = tmp_path / "objectives.db"
        with db.connect_closing(str(path)) as c1:
            obj = _make_objective(c1)
            assert db.record_blocked_replan(c1, obj.id) == 1
            obj_id = obj.id
        with db.connect_closing(str(path)) as c2:
            assert db.blocked_replan_attempts(c2, obj_id) == 1

    # Adaptation vs. the planned test: the legacy DDL mirrors SCHEMA_SQL's
    # objectives table exactly minus the counter column, including
    # `version INTEGER NOT NULL DEFAULT 1` (absent from the planned snippet).
    def test_legacy_store_migrates_in_place(self, tmp_path):
        """A pre-column store (objectives table built without the column)
        gains blocked_replan_attempts via connect()'s ALTER path, and existing
        rows read 0."""
        from hermes_cli import objectives_db as db

        path = tmp_path / "legacy.db"
        raw = sqlite3.connect(str(path))
        raw.executescript(
            """
            CREATE TABLE objectives (
                id                      TEXT PRIMARY KEY,
                organization_id         TEXT NOT NULL DEFAULT '__unscoped__',
                desired_outcome         TEXT NOT NULL,
                status                  TEXT NOT NULL,
                originator              TEXT NOT NULL,
                owner                   TEXT,
                constraints_json        TEXT NOT NULL,
                authority_scope_json    TEXT NOT NULL,
                success_criteria_json   TEXT NOT NULL,
                termination_json        TEXT NOT NULL,
                permitted_systems_json  TEXT NOT NULL,
                prohibited_actions_json TEXT NOT NULL,
                max_spend_minor         INTEGER,
                currency                TEXT,
                expires_at              INTEGER,
                reaffirmed_at           INTEGER NOT NULL,
                created_at              INTEGER NOT NULL,
                updated_at              INTEGER NOT NULL,
                version                 INTEGER NOT NULL DEFAULT 1
            );
            INSERT INTO objectives (
                id, desired_outcome, status, originator, constraints_json,
                authority_scope_json, success_criteria_json,
                termination_json, permitted_systems_json,
                prohibited_actions_json, reaffirmed_at, created_at, updated_at
            ) VALUES (
                'obj-legacy', 'outcome', 'accepted', 'setup', '[]', '{}',
                '[]', '[]', '[]', '[]', 0, 0, 0
            );
            """
        )
        raw.commit()
        raw.close()
        with db.connect_closing(str(path)) as c:
            cols = {r["name"] for r in c.execute("PRAGMA table_info(objectives)")}
            assert "blocked_replan_attempts" in cols
            row = c.execute(
                "SELECT blocked_replan_attempts FROM objectives WHERE id='obj-legacy'"
            ).fetchone()
            assert row["blocked_replan_attempts"] == 0


# ── Runtime policy application (Task 3) ────────────────────────────────────


class _NoActionPlanner:
    identity = "stub-planner"

    def propose(self, snapshot, event):
        from hermes_cli.objective_runtime import PlanProposal

        return PlanProposal(
            assumptions=[], tasks=["await guidance"], dependencies=[],
            risks=[], actions=[], objective_complete_when_verified=False,
        )


class _PassThroughExecutor:
    identity = "stub-executor"

    def execute(self, action, context):  # pragma: no cover - never reached
        raise AssertionError("no execution expected")


class _FailingVerifier:
    identity = "stub-verifier"

    def verify(self, action, result):  # pragma: no cover - never reached
        raise AssertionError("no action verification expected")

    def verify_objective(self, snapshot, proposal, results):
        from hermes_cli.objective_runtime import VerificationOutcome

        return VerificationOutcome("fail", "evidence insufficient")


def _make_runtime(conn, charter):
    from hermes_cli.objective_runtime import ObjectiveRuntime

    return ObjectiveRuntime(
        conn, charter=charter, planner=_NoActionPlanner(),
        executor=_PassThroughExecutor(), verifier=_FailingVerifier(),
        policy_version="test-v1",
    )


@pytest.fixture()
def autonomous_charter():
    return _charter()  # from Task 1 helper: autonomous policy


def _accepted_objective_with_event(conn):
    from hermes_cli import objectives_db as db

    obj = _make_objective(conn)
    db.transition_objective(conn, obj.id, "accepted", actor="test")
    db.enqueue_objective_event(
        conn, objective_id=obj.id, event_type="ceo.operating_review",
        payload={"source": "test"},
    )
    return obj


def _claim_one(conn):
    from hermes_cli import objectives_db as db

    return db.claim_objective_event(conn, runtime_id="test-runtime")


def _pending_replans(conn, objective_id):
    return conn.execute(
        "SELECT * FROM objective_inbox WHERE objective_id=? AND "
        "event_type='objective.replan' AND status='pending' "
        "ORDER BY created_at",
        (objective_id,),
    ).fetchall()


def _open_interventions(conn, objective_id, category):
    return conn.execute(
        "SELECT * FROM intervention_queue WHERE objective_id=? AND "
        "category=? AND status='open'",
        (objective_id, category),
    ).fetchall()


class TestAutonomousReplan:
    def test_no_admissible_action_replans_within_budget(
        self, conn, autonomous_charter
    ):
        from hermes_cli import objectives_db as db

        obj = _accepted_objective_with_event(conn)
        rt = _make_runtime(conn, autonomous_charter)
        claimed = _claim_one(conn)
        assert claimed is not None
        rt._run_claimed_event(claimed)

        assert db.blocked_replan_attempts(conn, obj.id) == 1
        current = db.get_objective(conn, obj.id)
        assert current.status == "planned"  # replanned, not parked
        replans = _pending_replans(conn, obj.id)
        assert len(replans) == 1
        assert _open_interventions(conn, obj.id, "no_admissible_action") == []
        # audit trail recorded
        audits = conn.execute(
            "SELECT * FROM business_audit_events WHERE objective_id=? AND "
            "event_type='objective.autonomous_replan'", (obj.id,)
        ).fetchall()
        assert len(audits) == 1

    def test_replan_event_carries_backoff(self, conn, autonomous_charter):
        import time as _time
        from hermes_cli import objectives_db as db

        obj = _accepted_objective_with_event(conn)
        rt = _make_runtime(conn, autonomous_charter)
        before = int(_time.time())
        claimed = _claim_one(conn)
        rt._run_claimed_event(claimed)
        replan = _pending_replans(conn, obj.id)[0]
        assert int(replan["available_at"]) >= before + 60  # charter backoff

    def test_attempts_exhausted_abandons_objective(self, conn, autonomous_charter):
        from hermes_cli import objectives_db as db

        obj = _accepted_objective_with_event(conn)
        # Burn the 2 allowed replans from the Task-1 charter.
        db.record_blocked_replan(conn, obj.id)
        db.record_blocked_replan(conn, obj.id)
        rt = _make_runtime(conn, autonomous_charter)
        claimed = _claim_one(conn)
        rt._run_claimed_event(claimed)

        current = db.get_objective(conn, obj.id)
        assert current.status == "abandoned"  # terminal, NEVER completed/verified
        assert db.blocked_replan_attempts(conn, obj.id) == 0  # reset on terminal
        audits = conn.execute(
            "SELECT * FROM business_audit_events WHERE objective_id=? AND "
            "event_type='objective.autonomous_abandon'", (obj.id,)
        ).fetchall()
        assert len(audits) == 1

    def test_budget_category_never_autonomously_resolved(
        self, conn, autonomous_charter, monkeypatch
    ):
        from hermes_cli import objectives_db as db
        from hermes_cli import resource_budget

        obj = _accepted_objective_with_event(conn)

        def explode(*a, **k):
            raise resource_budget.ResourceBudgetError(
                "objective budget exhausted"
            )

        monkeypatch.setattr(resource_budget, "assert_admissible", explode)
        rt = _make_runtime(conn, autonomous_charter)
        claimed = _claim_one(conn)
        rt._run_claimed_event(claimed)

        current = db.get_objective(conn, obj.id)
        assert current.status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0  # human-only: no counter
        assert len(
            _open_interventions(conn, obj.id, "resource_budget_exhausted")
        ) == 1

    def test_advise_mode_is_legacy_identical(self, conn):
        from hermes_cli import objectives_db as db

        charter = _charter(blocked_outcome_policy={"mode": "advise"})
        obj = _accepted_objective_with_event(conn)
        rt = _make_runtime(conn, charter)
        claimed = _claim_one(conn)
        rt._run_claimed_event(claimed)

        assert db.get_objective(conn, obj.id).status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0
        assert _pending_replans(conn, obj.id) == []
        assert len(
            _open_interventions(conn, obj.id, "no_admissible_action")
        ) == 1  # advisor handoff as before

    def test_operator_stop_wins_over_policy(self, conn, autonomous_charter):
        """Supervised operating mode (operator pause) prevents autonomous
        replanning even with an autonomous policy — stop controls win."""
        from hermes_cli import objectives_db as db

        charter = dict(autonomous_charter)
        charter["operating_mode"] = "supervised"
        obj = _accepted_objective_with_event(conn)
        rt = _make_runtime(conn, charter)
        claimed = _claim_one(conn)
        rt._run_claimed_event(claimed)

        assert db.get_objective(conn, obj.id).status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0

    def test_abandon_after_max_false_stays_blocked_and_demands_human(
        self, conn, autonomous_charter
    ):
        from hermes_cli import objectives_db as db

        charter = _charter(blocked_outcome_policy={
            "mode": "autonomous", "max_replan_attempts": 1,
            "abandon_after_max": False,
        })
        obj = _accepted_objective_with_event(conn)
        db.record_blocked_replan(conn, obj.id)  # burn the single attempt
        rt = _make_runtime(conn, charter)
        claimed = _claim_one(conn)
        rt._run_claimed_event(claimed)

        current = db.get_objective(conn, obj.id)
        assert current.status == "blocked"  # not abandoned
        assert len(
            _open_interventions(conn, obj.id, "no_admissible_action")
        ) == 1

    # Adaptation vs. the planned test: the verify branch persists its verdict
    # via record_verification, whose evidence contract requires a canonical
    # envelope — so the stub verifier emits one via verification_evidence.build
    # (no monkeypatches needed; verdict/evidence are orthogonal).
    def test_evidence_insufficient_replans_autonomously(
        self, conn, autonomous_charter
    ):
        """Path A: the verification-failure branch also replans under policy,
        with plan_id/verification_id evidence in the audit payload."""
        from hermes_cli import objectives_db as db
        from hermes_cli import verification_evidence
        from hermes_cli.objective_runtime import PlanProposal, VerificationOutcome

        class _CompletablePlanner(_NoActionPlanner):
            def propose(self, snapshot, event):
                return PlanProposal(
                    assumptions=[], tasks=["prove"], dependencies=[],
                    risks=[], actions=[],
                    objective_complete_when_verified=True,
                )

        class _ContractFailingVerifier(_FailingVerifier):
            def verify_objective(self, snapshot, proposal, results):
                evidence = verification_evidence.build(
                    observer=self.identity,
                    source_kind="deterministic_check",
                    source_reference="stub://success-criteria",
                    facts={"satisfied": False},
                )
                return VerificationOutcome("fail", evidence)

        obj = _accepted_objective_with_event(conn)
        rt = _make_runtime(conn, autonomous_charter)
        rt.planner = _CompletablePlanner()
        rt.verifier = _ContractFailingVerifier()
        claimed = _claim_one(conn)
        assert claimed is not None
        rt._run_claimed_event(claimed)

        current = db.get_objective(conn, obj.id)
        assert current.status == "planned"
        assert db.blocked_replan_attempts(conn, obj.id) == 1
        replans = _pending_replans(conn, obj.id)
        assert len(replans) == 1
        assert replans[0]["payload_json"] is not None
        audits = conn.execute(
            "SELECT payload_json FROM business_audit_events WHERE "
            "objective_id=? AND event_type='objective.autonomous_replan'",
            (obj.id,),
        ).fetchall()
        assert len(audits) == 1
        payload = json.loads(audits[0]["payload_json"])
        assert payload["policy_mode"] == "autonomous"
        assert payload["policy_version"] == "test-v1"

    def test_human_only_category_via_helper_falls_back(
        self, conn, autonomous_charter
    ):
        """The _HUMAN_ONLY_BLOCKED_CATEGORIES gate itself: a human-only
        category passed to the helper must raise the advisor handoff and
        never consume the counter — even in autonomous mode."""
        from hermes_cli import objectives_db as db

        obj = _accepted_objective_with_event(conn)
        rt = _make_runtime(conn, autonomous_charter)
        outcome = rt._resolve_blocked_outcome(
            event_id="evt-test",
            objective_id=obj.id,
            category="resource_budget_exhausted",
            reason="budget exhausted",
            context={"plan_id": "plan-x"},
            options=[{"id": "abandon", "label": "Abandon objective"}],
        )
        assert outcome.status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0
        assert len(
            _open_interventions(conn, obj.id, "resource_budget_exhausted")
        ) == 1

    # Adaptation vs. the planned test: "authorized" is only reachable from
    # "planned" (_TRANSITIONS); accepted→authorized raises ObjectiveStateError.
    def test_illegal_transition_does_not_burn_budget(
        self, conn, autonomous_charter
    ):
        """I1 regression: when the objective sits in a state whose
        planned-transition is illegal (authorized), the helper falls back to
        the advisor path WITHOUT consuming replan budget."""
        from hermes_cli import objectives_db as db

        obj = _accepted_objective_with_event(conn)
        db.transition_objective(conn, obj.id, "planned", actor="test")
        db.transition_objective(conn, obj.id, "authorized", actor="test")
        rt = _make_runtime(conn, autonomous_charter)
        outcome = rt._resolve_blocked_outcome(
            event_id="evt-test",
            objective_id=obj.id,
            category="no_admissible_action",
            reason="planner found no admissible next action",
            context={"plan_id": "plan-x"},
            options=[{"id": "advise", "label": "Provide bounded advisory guidance"}],
        )
        assert outcome.status == "blocked"
        assert db.blocked_replan_attempts(conn, obj.id) == 0
        # The advisor fallback transitioned authorized→blocked (legal).
        assert db.get_objective(conn, obj.id).status == "blocked"


class TestRestartDurability:
    # Adaptations vs. the planned snippet: connect() already sets
    # row_factory=sqlite3.Row (redundant per-conn assignment dropped); the
    # charter comes from the module-level _charter() helper
    # (autonomous_charter is a pytest fixture, not callable here); each
    # claimed event is finalized with finish_objective_event(status=
    # "completed") exactly as the real loop does after _run_claimed_event —
    # otherwise block #1's live claim keeps the one-claim-per-objective
    # guard blocking the post-restart claim; and the final durable-inbox
    # count is 1, not 2 — with max_replan_attempts=2 the second blocked
    # cycle records attempt 2 and ABANDONS instead of enqueuing a third
    # replan lifecycle.
    def test_replan_survives_restart(self, tmp_path):
        """The scheduled replan event is durable: a fresh runtime instance on
        the same store picks it up and continues the attempt sequence —
        counter and pending event survive process death, and the autonomous
        loop completes (abandon) across the restart."""
        from hermes_cli import objectives_db as db

        path = tmp_path / "restart-durability.db"
        with db.connect_closing(str(path)) as conn:
            obj = _accepted_objective_with_event(conn)
            rt = _make_runtime(conn, _charter())
            claimed = _claim_one(conn)
            assert claimed is not None
            rt._run_claimed_event(claimed)  # block #1 -> replan scheduled
            db.finish_objective_event(
                conn, claimed["id"], runtime_id="test-runtime",
                status="completed",
            )
            assert db.blocked_replan_attempts(conn, obj.id) == 1
            obj_id = obj.id

        # Simulate restart: zero the backoff so the event is due now, then a
        # fresh runtime instance on the same store.
        with db.connect_closing(str(path)) as conn2:
            conn2.execute(
                "UPDATE objective_inbox SET available_at = 0 "
                "WHERE event_type='objective.replan'"
            )
            conn2.commit()
            rt2 = _make_runtime(conn2, _charter())
            claimed2 = _claim_one(conn2)
            assert claimed2 is not None
            assert claimed2["event_type"] == "objective.replan"
            rt2._run_claimed_event(claimed2)  # block #2 -> attempt 2 of 2
            db.finish_objective_event(
                conn2, claimed2["id"], runtime_id="test-runtime",
                status="completed",
            )

            current = db.get_objective(conn2, obj_id)
            assert current.status == "abandoned"  # terminal, never completed
            assert db.blocked_replan_attempts(conn2, obj_id) == 0  # reset
            # Correction vs. the planned snippet: only ONE replan event was
            # ever enqueued (attempt 2 abandons rather than scheduling a
            # third lifecycle) — assert the real durable-inbox shape.
            total = conn2.execute(
                "SELECT COUNT(*) AS n FROM objective_inbox WHERE "
                "objective_id=? AND event_type='objective.replan'",
                (obj_id,),
            ).fetchone()
            assert total["n"] == 1
            # Both audit lifecycles survive the restart as durable evidence.
            audits = conn2.execute(
                "SELECT event_type, COUNT(*) AS n FROM business_audit_events "
                "WHERE objective_id=? AND event_type IN "
                "('objective.autonomous_replan','objective.autonomous_abandon') "
                "GROUP BY event_type",
                (obj_id,),
            ).fetchall()
            counts = {r["event_type"]: r["n"] for r in audits}
            assert counts == {
                "objective.autonomous_replan": 1,
                "objective.autonomous_abandon": 1,
            }
