# Post-Update Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]` syntax for tracking.

**Goal:** After every `hermes update` code swap + dependency sync, run a bounded functional canary (core import probes + entry-point smoke) and auto-rollback to the pre-pull SHA on failure — closing the gap where a runtime breakage passes the syntax-only guard and bricks the install until the next manual update.

**Architecture:** One new module (`hermes_cli/update_canary.py`) with a check registry (each check: name, fn → (ok, detail)), a per-check subprocess isolation (a broken import can't poison the updater process), and an overall time budget (~60s hard cap). Wired into `_cmd_update_impl` after the dependency sync and BEFORE gateway restart/fleet phases: canary fail → generalize the existing rollback (`git reset --hard pre_pull_sha`, same semantics as `_rollback_if_pulled_syntax_error`) + receipt step `post_update_canary` + exit 1. Config gate `updates.post_update_canary: true` (default ON — a healthy update passes in seconds; false = skip with a receipt skip-step).

**Tech Stack:** Python subprocess (isolated checks), existing receipt/rollback machinery, pytest via `scripts/run_tests.sh`.

**Governance invariants:**
1. Canary failure NEVER ships: fail → rollback + exit, same contract as the syntax guard (including the "recover manually" fallback when rollback fails).
2. Budget: the canary adds at most ~60s to a healthy update; every check is timeout-bounded (subprocess timeout, no unbounded waits).
3. Canary failure details land in the printed output AND the receipt (evidence for post-hoc review).
4. Skip is explicit and recorded (`post_update_canary` skip-step with reason), never silent.
5. Known limitation documented: after rollback, the venv may hold deps for the NEW code (pre-existing gap shared with the syntax guard; dependency-sync-after-rollback is a follow-up).

**Files:**
- Create: `hermes_cli/update_canary.py`
- Modify: `hermes_cli/update_cmd.py` (wire into `_cmd_update_impl`)
- Modify: `hermes_cli/config.py` DEFAULT_CONFIG (`updates.post_update_canary: true`)
- Create: `tests/hermes_cli/test_update_canary.py`
- Modify: `website/docs/guides/` or update docs (canary section)

---

### Task 1: Canary module (check registry + runner)

**Files:**
- Create: `hermes_cli/update_canary.py`
- Create: `tests/hermes_cli/test_update_canary.py`

- [ ] **Step 1: Failing tests**

```python
"""Post-update canary: bounded functional smoke after the code swap.

Fail → the update pipeline rolls back to the pre-pull SHA (same contract as
the syntax guard). Default ON (updates.post_update_canary); skip is
explicit and recorded.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


class TestCanaryChecks:
    def test_import_probe_passes_on_healthy_tree(self, tmp_path):
        from hermes_cli.update_canary import run_canary

        result = run_canary(project_root=Path(__file__).parent.parent.parent,
                            python_exe=sys.executable)
        assert result["verdict"] == "pass", result
        names = {c["name"] for c in result["checks"]}
        assert "core_imports" in names
        assert "entry_point" in names

    def test_import_probe_fails_on_broken_module(self, tmp_path, monkeypatch):
        """A core module that raises on import → canary fail with the module
        named in the detail."""
        from hermes_cli import update_canary as uc

        # Point the import probe at a tree with a broken core file.
        root = tmp_path / "proj"
        (root / "hermes_cli").mkdir(parents=True)
        (root / "hermes_cli" / "__init__.py").write_text("", encoding="utf-8")
        (root / "hermes_cli" / "config.py").write_text(
            "raise ImportError('simulated broken dep graph')\n", encoding="utf-8"
        )
        # Minimal check list pointing at hermes_cli.config
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES",
                            ["hermes_cli.config"])
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        failed = [c for c in result["checks"] if not c["ok"]]
        assert any("hermes_cli.config" in c["detail"] for c in failed)

    def test_entry_point_check_reports_failure(self, tmp_path, monkeypatch):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        root.mkdir()
        # entry_point runs `<python> -m hermes_cli.main --version` with
        # cwd=project_root; simulate failure via a broken module from (a).
        (root / "hermes_cli").mkdir()
        (root / "hermes_cli" / "__init__.py").write_text("", encoding="utf-8")
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", [])
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        # hermes_cli.main doesn't exist in this fake tree → entry_point fails
        assert result["verdict"] == "fail"
        entry = [c for c in result["checks"] if c["name"] == "entry_point"]
        assert entry and not entry[0]["ok"]

    def test_timeout_bounds_a_hanging_check(self, tmp_path, monkeypatch):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        root.mkdir()
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", [])
        monkeypatch.setattr(uc, "_CHECK_TIMEOUT", 2.0)
        # A check whose subprocess hangs: use a probe command that sleeps.
        monkeypatch.setattr(
            uc, "_ENTRY_POINT_ARGS",
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        entry = [c for c in result["checks"] if c["name"] == "entry_point"]
        assert "timed out" in entry[0]["detail"]

    def test_budget_cap(self, tmp_path, monkeypatch):
        """Overall time budget: checks beyond the budget are skipped and
        reported, verdict fails if a skipped check was mandatory."""
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        root.mkdir()
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", [])
        monkeypatch.setattr(uc, "_ENTRY_POINT_ARGS",
                            [sys.executable, "-c", "import time; time.sleep(60)"])
        monkeypatch.setattr(uc, "_CHECK_TIMEOUT", 2.0)
        monkeypatch.setattr(uc, "_BUDGET_SECONDS", 3.0)
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        # entry_point burns the budget; the run must terminate with a fail
        # verdict (not hang).
        assert result["verdict"] in {"fail", "error"}
```

(premise check: read `_UPDATE_CRITICAL_FILES` in update_cmd.py for the module list to mirror in `_CORE_IMPORT_PROBES`; read how the console entry point is declared in pyproject.toml (`[project.scripts]`) to define `_ENTRY_POINT_ARGS` — likely `[sys.executable, "-m", "hermes_cli.main", "--version"]` with a cwd=project_root and env carrying the venv.)

- [ ] **Step 2: RED** — run `scripts/run_tests.sh tests/hermes_cli/test_update_canary.py -j 1 -q`; record.

- [ ] **Step 3: Implement `hermes_cli/update_canary.py`:**

```python
"""Post-update canary: bounded functional smoke after the code swap.

Every check runs in a subprocess (a broken import cannot poison the updater
process) with a per-check timeout and an overall budget. Fail → the update
pipeline rolls back to the pre-pull SHA (same contract as the syntax guard).

Known limitation (shared with the syntax guard): after rollback the venv
may hold dependencies for the NEW code; a dependency re-sync after rollback
is a recorded follow-up.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import probes mirror the critical-file list in update_cmd.py (premise:
# read _UPDATE_CRITICAL_FILES and keep the module stems in sync).
_CORE_IMPORT_PROBES: List[str] = [
    "hermes_cli.config",
    "hermes_cli.main",
    "run_agent",
    "agent.auxiliary_client",
]

_CHECK_TIMEOUT = 30.0
_BUDGET_SECONDS = 60.0

# The console entry-point smoke (adapt from pyproject [project.scripts]).
_ENTRY_POINT_ARGS: List[str] = [sys.executable, "-m", "hermes_cli.main", "--version"]


def _run_check(name: str, argv: List[str], cwd: Path,
               deadline: float) -> Dict[str, Any]:
    """One subprocess check: (name, ok, detail). Timeout/exit-code aware."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {"name": name, "ok": False,
                "detail": "skipped: canary budget exhausted"}
    try:
        proc = subprocess.run(
            argv, cwd=str(cwd), capture_output=True, text=True,
            timeout=min(_CHECK_TIMEOUT, remaining),
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return {"name": name, "ok": False, "detail": "timed out"}
    except OSError as exc:
        return {"name": name, "ok": False, "detail": f"spawn failed: {exc}"}
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return {"name": name, "ok": False,
                "detail": f"exit {proc.returncode}: {tail[-1] if tail else ''}"}
    return {"name": name, "ok": True, "detail": ""}


def run_canary(*, project_root: Path,
               python_exe: str = sys.executable) -> Dict[str, Any]:
    """Run all canary checks. Returns {verdict: pass|fail, checks: [...],
    duration_seconds}."""
    started = time.monotonic()
    deadline = started + _BUDGET_SECONDS
    checks: List[Dict[str, Any]] = []

    # 1. Import probes — one combined subprocess (fast, one interpreter spin).
    if _CORE_IMPORT_PROBES:
        probe_code = "; ".join(f"import {m}" for m in _CORE_IMPORT_PROBES)
        checks.append(_run_check(
            "core_imports",
            [python_exe, "-c", probe_code],
            project_root, deadline,
        ))

    # 2. Entry-point smoke.
    checks.append(_run_check("entry_point", list(_ENTRY_POINT_ARGS),
                             project_root, deadline))

    passed = all(c["ok"] for c in checks)
    return {"verdict": "pass" if passed else "fail",
            "checks": checks,
            "duration_seconds": round(time.monotonic() - started, 1)}
```

(Adapt `_CORE_IMPORT_PROBES` from the real `_UPDATE_CRITICAL_FILES` stems — keep them in sync via a comment cross-reference; adapt `_ENTRY_POINT_ARGS` to the real console script + a fast flag. If `--version` is slow (imports the world), prefer `python -c "from hermes_cli.main import main"`-style import smoke instead — decide from the premise check and note it.)

- [ ] **Step 4: GREEN** — expect 5 passed.
- [ ] **Step 5: Commit** — `feat(update): post-update canary module (bounded functional smoke)`

---

### Task 2: Pipeline wiring + rollback integration

**Files:**
- Modify: `hermes_cli/update_cmd.py`
- Test: `tests/hermes_cli/test_update_canary.py`

- [ ] **Step 1: Failing tests** (wiring-level, monkeypatched):

```python
class TestPipelineWiring:
    def test_canary_failure_triggers_rollback_and_exit(self, monkeypatch, tmp_path):
        """Wire-level: canary fail → reset --hard pre_pull_sha → receipt
        step recorded → SystemExit(1). The existing dependency-sync happens
        BEFORE the canary; patch the seams around it."""
        from hermes_cli import update_canary as uc

        monkeypatch.setattr(uc, "run_canary",
                            lambda **k: {"verdict": "fail", "checks": [
                                {"name": "core_imports", "ok": False,
                                 "detail": "exit 1: ImportError"}],
                            "duration_seconds": 2.0})
        # premise: read _cmd_update_impl's post-dependency-sync section to
        # find the canary call site; test via a narrow seam — e.g. patch
        # the module attribute update_cmd._run_post_update_canary (the
        # wrapper this task adds) to the failing canary, patch the git run
        # + sys.exit, and drive the minimal surrounding function
        # (_post_update_phase or equivalent). The CONTRACT: canary fail →
        # git reset --hard <pre_pull_sha> called → receipt step
        # 'post_update_canary' ok=False → sys.exit(1).

    def test_canary_pass_continues_pipeline(self, monkeypatch):
        """Canary pass → no rollback, no exit; the pipeline proceeds to the
        gateway/fleet phase (patched seam returns pass; the subsequent
        phase-call is observed via a recorder)."""

    def test_skipped_canary_recorded(self, monkeypatch):
        """updates.post_update_canary=false → receipt skip-step, no canary
        subprocess, pipeline continues."""
```

(The wiring tests require reading `_cmd_update_impl`'s flow to find the narrowest testable seam: the plan recommends extracting a tiny `_run_post_update_canary(pre_pull_sha, git_cmd) -> None` function in update_cmd.py (calls run_canary, prints, records receipt, rolls back, exits) so the wiring test drives THAT function with monkeypatched run_canary/_git_run/sys.exit instead of the whole _cmd_update_impl. Prefer the seam extraction — it matches the file's existing `_m()` delegation style.)

- [ ] **Step 2: RED** — record.
- [ ] **Step 3: Implement in `hermes_cli/update_cmd.py`:**

```python
def _run_post_update_canary(pre_pull_sha: str, git_cmd) -> None:
    """Bounded functional smoke after the code swap + dependency sync.
    Fail → rollback to pre_pull_sha (same contract as the syntax guard) and
    exit 1. Recorded in the receipt as post_update_canary."""
    from hermes_cli.config import load_config
    from hermes_cli import update_canary

    enabled = True
    try:
        enabled = bool(
            (load_config().get("updates") or {}).get("post_update_canary", True)
        )
    except Exception:
        pass  # config unreadable: default ON (fail-closed canary)
    if not enabled:
        _record_update_step("post_update_canary", None,
                            "skipped by updates.post_update_canary=false")
        return

    print("⚕ Running post-update canary...")
    result = update_canary.run_canary(
        project_root=_m().PROJECT_ROOT,
        python_exe=sys.executable,
    )
    for check in result["checks"]:
        status = "✓" if check["ok"] else "✗"
        detail = f" — {check['detail']}" if check["detail"] else ""
        print(f"  {status} {check['name']}{detail}")
    _record_update_step(
        "post_update_canary", result["verdict"] == "pass",
        f"verdict={result['verdict']} duration={result['duration_seconds']}s")
    if result["verdict"] == "pass":
        return
    print()
    print("✗ Post-update canary FAILED — rolling back to the previous version.")
    if pre_pull_sha:
        rollback = _git_run(git_cmd, ["reset", "--hard", pre_pull_sha])
        if rollback.returncode == 0:
            print("  ✓ Rollback complete — your install is unchanged.")
            print("  Try ``hermes update`` again later once a fix lands.")
        else:
            print("  ✗ Rollback failed. Recover manually with:")
            print(f"    cd {_m().PROJECT_ROOT} && git reset --hard {pre_pull_sha}")
        _record_update_step("post_update_canary_rollback", rollback.returncode == 0,
                            f"to {pre_pull_sha[:10]}")
    else:
        print("  Could not capture pre-pull SHA — recover manually with:")
        print("    cd <install> && git reflog && git reset --hard <prev-sha>")
    sys.exit(1)
```

Call it in `_cmd_update_impl` after the dependency-sync section and before the gateway/fleet restart phases (find the exact seam by reading the flow — premise: the canary must run AFTER deps sync (else probes test stale deps) and BEFORE any gateway restart). `_record_update_step` is the existing best-effort receipt wrapper (update_cmd.py:144).

- [ ] **Step 4: GREEN** — wiring tests + Task 1 tests (expect 5 + 3 = 8+ passed).
- [ ] **Step 5: Regression** — `scripts/run_tests.sh tests/hermes_cli/ -k "update" -j 4 -q` (record; large suite — report failures vs stash baseline).
- [ ] **Step 6: Commit** — `feat(update): wire post-update canary into the update pipeline`

---

### Task 3: Config key + docs

**Files:**
- Modify: `hermes_cli/config.py` (`updates.post_update_canary: true` in DEFAULT_CONFIG)
- Modify: the update docs (find `website/docs/` update guide)

- [ ] **Step 1:** config key + `scripts/run_tests.sh tests/hermes_cli/test_config.py -j 1 -q` (record vs stash baseline).
- [ ] **Step 2:** docs section: what the canary checks, the ~60s budget, fail→rollback contract, the skip flag, the dep-sync-after-rollback limitation.
- [ ] **Step 3:** Commit — `docs+config: post_update_canary flag + update guide section`

---

### Task 4: Final review

Full-range diff review (invariants traced: fail→rollback+exit contract, budget bounds, receipt evidence, skip recorded), suite runs, follow-up list (dependency-sync-after-rollback, gateway-health-gated rollback as a second canary phase, canary check for the objective runtime / kanban dispatcher liveness under charter).

Self-review note: the canary must NOT run inside the gateway process or hold locks — subprocess isolation handles the poison case; the budget caps the updater wall-clock; and the receipt evidence must land even when the canary is skipped (skip-step). The wiring seam extraction (`_run_post_update_canary`) keeps `_cmd_update_impl` (a ~thousand-line function) untouched apart from one call — do not restructure the updater.
