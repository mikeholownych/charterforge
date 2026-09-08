"""Post-update canary: bounded functional smoke after the code swap.

Fail → the update pipeline rolls back to the pre-pull SHA (same contract as
the syntax guard). Default ON (updates.post_update_canary); skip is
explicit and recorded.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest


class TestCanaryChecks:
    def test_import_probe_passes_on_healthy_tree(self):
        from hermes_cli.update_canary import run_canary

        result = run_canary(
            project_root=Path(__file__).parent.parent.parent,
            python_exe=sys.executable,
        )
        assert result["verdict"] == "pass", result
        names = {c["name"] for c in result["checks"]}
        assert "core_imports" in names
        assert "entry_point" in names

    def test_import_probe_fails_on_broken_module(self, tmp_path, monkeypatch):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        (root / "hermes_cli").mkdir(parents=True)
        (root / "hermes_cli" / "__init__.py").write_text("", encoding="utf-8")
        (root / "hermes_cli" / "config.py").write_text(
            "raise ImportError('simulated broken dep graph')\n", encoding="utf-8"
        )
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", ["hermes_cli.config"])
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        failed = [c for c in result["checks"] if not c["ok"]]
        assert any("hermes_cli.config" in c["detail"] for c in failed)

    def test_combined_probe_identifies_each_failing_module(
        self, tmp_path, monkeypatch
    ):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        (root / "pkg").mkdir(parents=True)
        (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
        (root / "pkg" / "good.py").write_text("x = 1\n", encoding="utf-8")
        (root / "pkg" / "bad.py").write_text(
            "raise ImportError('simulated')\n", encoding="utf-8"
        )
        monkeypatch.setattr(
            uc, "_CORE_IMPORT_PROBES", ["pkg.good", "pkg.bad"]
        )
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        probe = [c for c in result["checks"] if c["name"] == "core_imports"][0]
        assert "pkg.bad" in probe["detail"]

    def test_entry_point_check_reports_failure(self, tmp_path, monkeypatch):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        (root / "hermes_cli").mkdir(parents=True)
        (root / "hermes_cli" / "__init__.py").write_text("", encoding="utf-8")
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", [])
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        entry = [c for c in result["checks"] if c["name"] == "entry_point"]
        assert entry and not entry[0]["ok"]

    def test_timeout_bounds_a_hanging_check(self, tmp_path, monkeypatch):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        root.mkdir()
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", [])
        monkeypatch.setattr(uc, "_CHECK_TIMEOUT", 2.0)
        monkeypatch.setattr(
            uc, "_ENTRY_POINT_ARGS",
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        entry = [c for c in result["checks"] if c["name"] == "entry_point"]
        assert "timed out" in entry[0]["detail"]

    def test_budget_cap(self, tmp_path, monkeypatch):
        from hermes_cli import update_canary as uc

        root = tmp_path / "proj"
        root.mkdir()
        monkeypatch.setattr(uc, "_CORE_IMPORT_PROBES", [])
        monkeypatch.setattr(
            uc, "_ENTRY_POINT_ARGS",
            [sys.executable, "-c", "import time; time.sleep(60)"],
        )
        monkeypatch.setattr(uc, "_CHECK_TIMEOUT", 2.0)
        monkeypatch.setattr(uc, "_BUDGET_SECONDS", 3.0)
        result = uc.run_canary(project_root=root, python_exe=sys.executable)
        assert result["verdict"] == "fail"
        entry = [c for c in result["checks"] if c["name"] == "entry_point"]
        assert "timed out" in entry[0]["detail"]


class TestPipelineWiring:
    def test_canary_failure_triggers_rollback_and_exit(self, monkeypatch):
        """Seam-level: canary fail → reset --hard pre_pull_sha → receipt
        step recorded → SystemExit(1)."""
        from hermes_cli import update_canary as uc
        from hermes_cli import update_cmd as ucmd

        monkeypatch.setattr(
            uc, "run_canary",
            lambda **k: {"verdict": "fail", "checks": [
                {"name": "core_imports", "ok": False,
                 "detail": "exit 1: ImportError"}],
            "duration_seconds": 2.0},
        )
        resets = []
        monkeypatch.setattr(
            ucmd, "_git_run",
            lambda git_cmd, args: resets.append(args)
            or type("R", (), {"returncode": 0, "stderr": ""})(),
        )
        exits = []
        monkeypatch.setattr(ucmd.sys, "exit", lambda code=0: exits.append(code))
        steps = []
        monkeypatch.setattr(
            ucmd, "_record_update_step",
            lambda name, ok, detail="": steps.append((name, ok, detail)),
        )
        # premise: _m() returns the hermes_cli.main module, so this patches
        # the module attribute directly.
        monkeypatch.setattr(ucmd._m(), "PROJECT_ROOT", Path("."), raising=False)
        # Suppress the prints for test cleanliness.
        monkeypatch.setattr(ucmd.sys, "stdout", io.StringIO())

        ucmd._run_post_update_canary("pre123", git_cmd=None)
        assert any(
            a[:2] == ["reset", "--hard"] and a[2] == "pre123" for a in resets
        )
        assert exits == [1]
        assert any(
            s[0] == "post_update_canary" and s[1] is False for s in steps
        )
        assert any(s[0] == "post_update_canary_rollback" for s in steps)

    def test_canary_pass_continues_pipeline(self, monkeypatch):
        """Canary pass → no rollback, no exit; pipeline continues."""
        from hermes_cli import update_canary as uc
        from hermes_cli import update_cmd as ucmd

        monkeypatch.setattr(
            uc, "run_canary",
            lambda **k: {"verdict": "pass", "checks": [
                {"name": "core_imports", "ok": True, "detail": ""}],
            "duration_seconds": 3.0},
        )
        resets = []
        monkeypatch.setattr(
            ucmd, "_git_run",
            lambda git_cmd, args: resets.append(args)
            or type("R", (), {"returncode": 0, "stderr": ""})(),
        )
        exits = []
        monkeypatch.setattr(ucmd.sys, "exit", lambda code=0: exits.append(code))
        steps = []
        monkeypatch.setattr(
            ucmd, "_record_update_step",
            lambda name, ok, detail="": steps.append((name, ok, detail)),
        )
        monkeypatch.setattr(ucmd.sys, "stdout", io.StringIO())

        ucmd._run_post_update_canary("pre123", git_cmd=None)
        assert resets == []  # no rollback on pass
        assert exits == []
        assert any(
            s[0] == "post_update_canary" and s[1] is True for s in steps
        )

    def test_skipped_canary_recorded(self, monkeypatch):
        """updates.post_update_canary=false → receipt skip-step, no canary
        subprocess, pipeline continues."""
        from hermes_cli import update_canary as uc
        from hermes_cli import update_cmd as ucmd
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"updates": {"post_update_canary": False}},
        )
        steps = []
        monkeypatch.setattr(
            ucmd, "_record_update_step",
            lambda name, ok, detail="": steps.append((name, ok, detail)),
        )
        canary_called = []
        monkeypatch.setattr(
            uc, "run_canary", lambda **k: canary_called.append(1),
        )
        monkeypatch.setattr(ucmd.sys, "stdout", io.StringIO())

        ucmd._run_post_update_canary("pre123", git_cmd=None)
        assert canary_called == []
        assert any(
            s[0] == "post_update_canary" and s[1] is None for s in steps
        )
