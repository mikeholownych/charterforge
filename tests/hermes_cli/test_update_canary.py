"""Post-update canary: bounded functional smoke after the code swap.

Fail → the update pipeline rolls back to the pre-pull SHA (same contract as
the syntax guard). Default ON (updates.post_update_canary); skip is
explicit and recorded.
"""
from __future__ import annotations

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
        assert result["verdict"] in {"fail", "error"}
