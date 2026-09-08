# Charter-Scoped Auxiliary Provider Authority Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Under an agentic charter that declares `authorized_providers`, auxiliary LLM calls (primary route and every fallback candidate) are restricted to those providers — fail-closed — so governed planning/judging can never silently route to an operator-unauthorized backend.

**Architecture:** One authority read (`hermes_cli/objective_policy.py::authorized_auxiliary_providers(charter)`) plus one filter function in `agent/auxiliary_client.py`. The filter applies at three resolved choke-points: the task `fallback_chain` entry loop inside `_try_configured_fallback_chain`, the main-fallback candidate acceptance inside `_call_llm_impl`'s fallback walk, and the primary-route acceptance at `_call_llm_impl` entry. Unauthorized candidates are skipped with a single debug trace each; if no authorized candidate exists the call raises `AuxiliaryProviderNotAuthorized` (typed, importable) rather than degrading silently. No charter key set (default) = zero behavior change.

**Tech Stack:** Python, pytest via `scripts/run_tests.sh`.

**Governance invariants:**
1. No `authorized_providers` (or empty) → identical behavior to today (no filtering anywhere).
2. Charter set + `agentic.enabled` → unauthorized providers are skipped in ALL aux fallback paths for charter-restricted tasks; never silently routed.
3. Fail-closed: authorized list non-empty and no candidate qualifies → typed error naming the task, the attempted providers, and the boundary — the objective cycle's existing retry/replan handling treats it as a transient-ish failure (recorded, audited), NOT a silent cross-authority call.
4. The filter reads the charter from the same config load the runtime uses; a mid-flight charter change applies on the next call (no caching beyond the existing config cache).
5. Audit: every skip is logged (logger.debug with task/provider/reason); every fail-closed raise carries attempted-provider evidence in the exception.

**Files:**
- Modify: `hermes_cli/objective_policy.py` (authority read helper)
- Modify: `agent/auxiliary_client.py` (filter + typed error + choke-point application)
- Create: `tests/agent/test_charter_provider_authority.py`

---

### Task 1: Charter authority read + typed error

**Files:**
- Modify: `hermes_cli/objective_policy.py`
- Modify: `agent/auxiliary_client.py` (error class only)
- Test: `tests/agent/test_charter_provider_authority.py`

- [ ] **Step 1: Failing tests**

```python
"""Charter-scoped auxiliary provider authority.

Under an agentic charter declaring authorized_providers, auxiliary LLM calls
are restricted to those providers — fail-closed — so governed planning and
judging never silently route to an operator-unauthorized backend.
"""
from __future__ import annotations

import pytest

from hermes_cli import objective_policy


class TestAuthorizedAuxiliaryProviders:
    def test_absent_charter_returns_none(self):
        assert objective_policy.authorized_auxiliary_providers({}) is None

    def test_disabled_charter_returns_none(self):
        charter = {"enabled": False,
                   "authorized_providers": ["openrouter"]}
        assert objective_policy.authorized_auxiliary_providers(charter) is None

    def test_nonempty_list_normalized(self):
        charter = {"enabled": True,
                   "authorized_providers": ["OpenRouter", " nous ", "NOUS"]}
        assert objective_policy.authorized_auxiliary_providers(charter) == {
            "openrouter", "nous"
        }

    def test_empty_list_means_no_restriction(self):
        charter = {"enabled": True, "authorized_providers": []}
        assert objective_policy.authorized_auxiliary_providers(charter) is None

    def test_non_list_rejected_by_validate_charter(self):
        with pytest.raises(ValueError, match="authorized_providers"):
            objective_policy.validate_charter({
                "enabled": True, "operating_mode": "autonomous",
                "max_autonomous_risk": "medium", "permit_ttl_seconds": 300,
                "runtime_host": "gateway",
                "authorized_providers": "openrouter",
            })

    def test_non_string_entries_rejected(self):
        with pytest.raises(ValueError, match="authorized_providers"):
            objective_policy.validate_charter({
                "enabled": True, "operating_mode": "autonomous",
                "max_autonomous_risk": "medium", "permit_ttl_seconds": 300,
                "runtime_host": "gateway",
                "authorized_providers": ["openrouter", 42],
            })


class TestTypedError:
    def test_error_carries_evidence(self):
        from agent.auxiliary_client import AuxiliaryProviderNotAuthorized

        err = AuxiliaryProviderNotAuthorized(
            task="objective_planner",
            attempted=["openrouter", "nous"],
            authorized={"nous"},
        )
        assert err.task == "objective_planner"
        assert err.attempted == ["openrouter", "nous"]
        assert err.authorized == {"nous"}
        assert "objective_planner" in str(err)
        assert "nous" in str(err)  # authorized names visible for diagnosis
```

- [ ] **Step 2: RED** — run `scripts/run_tests.sh tests/agent/test_charter_provider_authority.py -j 1 -q`; record (AttributeError: no attribute authorized_auxiliary_providers; ImportError for the error class).

- [ ] **Step 3: Implement**

In `hermes_cli/objective_policy.py` (module level, after validate_charter):

```python
def authorized_auxiliary_providers(
    charter: Mapping[str, Any],
) -> Optional[frozenset[str]]:
    """Providers auxiliary calls may use while this charter governs the
    runtime, normalized to lowercase; None when the charter does not restrict
    providers (absent/disabled charter or empty list = unrestricted)."""
    if not isinstance(charter, Mapping) or not bool(charter.get("enabled", False)):
        return None
    listed = charter.get("authorized_providers")
    if not isinstance(listed, list) or not listed:
        return None
    return frozenset(
        str(entry).strip().lower() for entry in listed if str(entry).strip()
    )
```

And in `validate_charter` (after the blocked_outcome_policy block):

```python
    authorized = charter.get("authorized_providers")
    if authorized is not None:
        if not isinstance(authorized, list) or any(
            not isinstance(entry, str) or not entry.strip()
            for entry in authorized
        ):
            raise ValueError(
                "agentic.authorized_providers must be a list of non-empty "
                "provider names"
            )
```

In `agent/auxiliary_client.py` (module level, near the top after imports):

```python
class AuxiliaryProviderNotAuthorized(RuntimeError):
    """Raised fail-closed when a charter's authorized_providers boundary
    leaves no admissible auxiliary provider for a governed call."""

    def __init__(self, *, task: str, attempted: list, authorized: frozenset):
        self.task = task
        self.attempted = list(attempted)
        self.authorized = set(authorized)
        super().__init__(
            f"auxiliary task {task!r}: attempted providers "
            f"{self.attempted} are outside the charter's authorized "
            f"providers {sorted(self.authorized)} — call refused "
            f"(fail-closed authority boundary)"
        )
```

- [ ] **Step 4: GREEN** — same command; expect 7 passed.
- [ ] **Step 5: Regression** — `scripts/run_tests.sh tests/hermes_cli/test_objective_policy.py tests/hermes_cli/test_objective_blocked_outcome_policy.py -j 2 -q` → expect 10 + 28 passed.
- [ ] **Step 6: Commit** — `feat(agentic): charter authorized_providers read + typed aux boundary error`

---

### Task 2: Filter application at the choke-points

**Files:**
- Modify: `agent/auxiliary_client.py`
- Test: `tests/agent/test_charter_provider_authority.py`

- [ ] **Step 1: Failing tests** (behavioral, through the real functions)

```python
class TestChokePointFiltering:
    @pytest.fixture()
    def charter_restricted(self, monkeypatch):
        """Agentic charter enabled with authorized_providers=[nous]."""
        from hermes_cli import objective_policy as op

        monkeypatch.setattr(
            op, "authorized_auxiliary_providers",
            lambda charter=None: frozenset({"nous"}),
        )
        # Auxiliary config read: give the task a chain with one authorized
        # and one unauthorized entry.
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {
                "fallback_chain": [
                    {"provider": "openrouter", "model": "m-open"},
                    {"provider": "nous", "model": "m-nous"},
                ],
            }}},
        )
        monkeypatch.setattr(
            "agent.auxiliary_client.load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {
                "fallback_chain": [
                    {"provider": "openrouter", "model": "m-open"},
                    {"provider": "nous", "model": "m-nous"},
                ],
            }}},
        ) if hasattr(__import__("agent.auxiliary_client", fromlist=["x"]),
                     "load_config_readonly") else None

    def test_task_chain_skips_unauthorized_entry(
        self, charter_restricted, monkeypatch
    ):
        """_try_configured_fallback_chain must not return the unauthorized
        openrouter candidate; it returns the nous entry."""
        from agent import auxiliary_client as aux

        resolved = {"called": []}

        def fake_resolve(entry):
            resolved["called"].append(entry.get("provider"))
            provider = entry.get("provider")
            client = type("C", (), {"base_url": f"https://{provider}.test"})()
            return client, entry.get("model")

        monkeypatch.setattr(aux, "_resolve_fallback_entry", fake_resolve)
        monkeypatch.setattr(
            aux, "_context_too_small", lambda *a, **k: None
        )

        client, model, label = aux._try_configured_fallback_chain(
            "objective_planner", "auto", reason="test"
        )
        # The unauthorized entry was never even resolved.
        assert resolved["called"] == ["nous"]
        assert client is not None
        assert "nous" in label

    def test_no_authorized_candidate_raises_fail_closed(
        self, charter_restricted, monkeypatch
    ):
        """All chain entries unauthorized → AuxiliaryProviderNotAuthorized
        with attempted-provider evidence (NOT a silent empty return)."""
        import hermes_cli.config as config_mod
        from agent import auxiliary_client as aux

        monkeypatch.setattr(
            config_mod, "load_config_readonly",
            lambda: {"auxiliary": {"objective_planner": {
                "fallback_chain": [{"provider": "openrouter"}],
            }}},
        )
        monkeypatch.setattr(
            aux, "_resolve_fallback_entry",
            lambda entry: (type("C", (), {"base_url": "x"})(), "m"),
        )
        monkeypatch.setattr(aux, "_context_too_small", lambda *a, **k: None)

        with pytest.raises(aux.AuxiliaryProviderNotAuthorized) as excinfo:
            aux._try_configured_fallback_chain(
                "objective_planner", "auto", reason="test"
            )
        assert "openrouter" in excinfo.value.attempted
```

( premise note for implementer: verify which module-level name the chain reader actually imports `load_config_readonly` from — `_get_auxiliary_task_config` imports `hermes_cli.config.load_config_readonly` inline, so patch THAT import site; adapt the monkeypatch targets to the real code after reading it.)

- [ ] **Step 2: RED** — record.

- [ ] **Step 3: Implement in `agent/auxiliary_client.py`:**

(a) Authority read (module level):

```python
def _charter_provider_boundary() -> Optional[frozenset]:
    """Authorized-provider set from the active agentic charter, or None when
    unrestricted. Reads the same config the runtime governs with; failures
    are fail-open to unrestricted ONLY when the charter cannot be read at all
    (config load failure) — a present-but-restrictive charter always applies."""
    try:
        from hermes_cli.config import load_config_readonly
        from hermes_cli.objective_policy import authorized_auxiliary_providers

        charter = (load_config_readonly() or {}).get("agentic") or {}
        return authorized_auxiliary_providers(charter)
    except Exception:
        return None
```

(b) In `_try_configured_fallback_chain`, after reading `chain`, add:

```python
    boundary = _charter_provider_boundary()
    unauthorized_attempted: list[str] = []
    authorized_candidates: list[tuple[int, dict]] = []
    if boundary is not None:
        for i, entry in enumerate(chain):
            if not isinstance(entry, dict):
                continue
            fb_provider = str(entry.get("provider", "")).strip().lower()
            if fb_provider and fb_provider not in boundary:
                unauthorized_attempted.append(fb_provider)
                logger.debug(
                    "Auxiliary %s: skipping fallback_chain[%d] provider %r — "
                    "outside charter authorized_providers %s",
                    task, i, fb_provider, sorted(boundary))
                continue
            authorized_candidates.append((i, entry))
        chain = [entry for _i, entry in authorized_candidates]
    else:
        unauthorized_attempted = []
```

and restructure the existing loop to iterate the (possibly filtered) chain while retaining original indices for labels. After the loop, before the final `return None, None, ""`:

```python
    if boundary is not None and unauthorized_attempted and not tried:
        raise AuxiliaryProviderNotAuthorized(
            task=task, attempted=unauthorized_attempted, authorized=boundary
        )
```

(The precise fail-closed condition — raise when NO authorized candidate produced a client AND at least one unauthorized was skipped — must be reasoned by the implementer against the loop's flow: if an authorized entry existed but failed to build a client, that's a normal chain exhaustion (no raise); raise ONLY when every attempted entry was unauthorized. Adjust and document the final rule in a comment.)

(c) Primary-route acceptance: in `_call_llm_impl` (or `_resolve_route_for_call`-equivalent — find the single place the PRIMARY provider is resolved before the call), add the boundary check: if boundary is not None and the primary provider (when explicitly pinned, not "auto") is unauthorized → raise the typed error immediately with attempted=[primary]. Auto-primary: leave as-is for this plan (the chain filter governs fallbacks; the primary under charter mode is the operator's own model config — document this asymmetry in the helper docstring).

- [ ] **Step 4: GREEN** — same file; expect all green.
- [ ] **Step 5: Regression** — `scripts/run_tests.sh tests/agent/ -k "auxiliary" -j 4 -q` (record counts; report unrelated failures separately), plus Task 1's suites.
- [ ] **Step 6: Commit** — `feat(agentic): charter-scoped auxiliary fallback filtering`

---

### Task 3: Planner-level evidence (audit trail)

**Files:**
- Modify: `hermes_cli/objective_adapters.py` (capture typed error into planner_inferences with parse_status="authority_refused")
- Test: `tests/agent/test_charter_provider_authority.py`

- [ ] **Step 1: Failing test**

```python
class TestPlannerAuthorityEvidence:
    def test_planner_records_authority_refusal(self, tmp_path, monkeypatch):
        """When the boundary refuses the planner call, the durable
        planner_inferences record shows parse_status='authority_refused' with
        the error — post-hoc review can see WHY planning did not happen."""
        from hermes_cli import objective_adapters, planner_inferences

        recorded = []

        class _FakeConn:
            def execute(self, *a, **k):  # pragma: no cover
                raise AssertionError("no SQL expected")

        monkeypatch.setattr(
            planner_inferences, "record",
            lambda *a, **k: recorded.append(k),
        )
        from agent import auxiliary_client as aux

        def refuse(**kwargs):
            raise aux.AuxiliaryProviderNotAuthorized(
                task="objective_planner",
                attempted=["openrouter"],
                authorized=frozenset({"nous"}),
            )

        monkeypatch.setattr(aux, "call_llm", refuse)

        contract = objective_adapters.RegisteredActionContract(
            action_type="noop", payload_schema={}, target_system="none",
            required_capability="noop.cap", verification_method="manual",
        )
        planner = objective_adapters.AuxiliaryObjectivePlanner(
            action_contracts=[contract],
        )
        with pytest.raises(aux.AuxiliaryProviderNotAuthorized):
            planner.propose(
                {"id": "obj-1", "desired_outcome": "x", "status": "planned",
                 "constraints": [], "success_criteria": [], "termination": [],
                 "permitted_systems": [], "prohibited_actions": [],
                 "max_spend_minor": 0, "plans": [], "actions": [],
                 "verifications": []},
                {"event_type": "ceo.operating_review", "payload": {},
                 "attempts": 0, "id": "evt-1"},
            )
        assert recorded and recorded[0]["parse_status"] == "authority_refused"
```

(premise checks: RegisteredActionContract's real fields; planner.propose's record path — the existing except-branch calls planner_inferences.record with parse_status="call_failed"; extend that branch to detect AuxiliaryProviderNotAuthorized and record "authority_refused" instead, keeping the re-raise.)

- [ ] **Step 2-4: RED → implement (extend the existing except branch in AuxiliaryObjectivePlanner.propose) → GREEN.**
- [ ] **Step 5: Regression** — objective family suites.
- [ ] **Step 6: Commit** — `feat(agentic): planner records authority_refused inference evidence`

---

### Task 4: Docs + charter setup exposure

**Files:**
- Modify: `website/docs/guides/agentic-business-os.md`
- Modify: `hermes_cli/setup.py` (same skip-on-exhaustion prompt pattern as feature 1 Task 5)

- [ ] **Step 1:** Document `authorized_providers` in the guide next to blocked_outcome_policy (boundary semantics: applies to auxiliary calls; fail-closed; default unrestricted; auto-primary asymmetry).
- [ ] **Step 2:** Optional setup prompt (skips on exhausted answer stream): "Restrict auxiliary model providers to an authorized list?" → if yes, comma-separated provider slugs → `config["agentic"]["authorized_providers"]`.
- [ ] **Step 3:** Run `scripts/run_tests.sh tests/hermes_cli/test_setup_agentic.py -j 1 -q` → no NEW failures vs the known pre-existing one.
- [ ] **Step 4: Commit** — `docs+setup: charter authorized_providers boundary`

---

### Task 5: Final review

- Full feature diff review (scope, invariants traced), all suite runs, follow-up list (payment-fallback/discovery-chain coverage under boundary — flag if those paths bypass the task-chain filter; decide follow-up vs in-scope).

Self-review note: the plan's Task 2 must NOT claim coverage of `_try_main_fallback_chain`, `_try_payment_fallback`, `_try_discovery_chain` — those read the MAIN agent's fallback config and the discovery chain, which are outside the task's chain. Either route them through the same boundary check (recommended: one shared `_boundary_allows(provider)` predicate called at each candidate-acceptance site) or explicitly scope the feature to task chains + primary and record the rest as follow-ups. The implementer should make the shared predicate the core deliverable and apply it at as many acceptance sites as cleanly reachable, documenting exactly which sites are covered.

## Status: COMPLETE (2026-09-06)

Commits ac9f1b71cc..f37154253d. Final review verdict READY — 19/19 charter
suite, 38/38 policy suites, 53/53 objective family, 15/15 db, setup +1P/1✗
(pre-existing), auxiliary 169✓/29✗ (byte-identical to base). Governance
contract traced on the riskiest lines: explicit-branch boundary check on the
wire provider (post-MoA unwrap, pre-client-build), task-chain fail-closed
condition (skip taxonomy documented incl. backend-skip semantics), and the
authority_refused end-to-end propagation (raise sites escape all retry
layers → planner records durably → re-raise). A production masking bug was
caught and fixed en route: planner_inferences' parse_status validation set
now accepts "authority_refused" (RED reproduced the exact ValueError mask).

Follow-ups (non-blocking, honestly documented in docstrings + guide):
1. Three unfenced aux ladders: _try_main_fallback_chain, _try_payment_fallback,
   _try_discovery_chain (and the vision-branch resolve path).
2. Auto-primary + cached-client laziness: boundary tightening applies
   immediately to chains, lazily to cached primaries; eviction-on-change
   flagged.
3. MoA aggregator-listing guidance for charter authors (explicit `moa`
   unwraps to the aggregator wire provider before judgment).
4. Ladder-path consequence: an authorized primary's payment/timeout failure
   can be re-branded as authority refusal when the rest of the chain is
   unauthorized (acceptable in partial-coverage state; revisit with the
   coverage follow-up).
