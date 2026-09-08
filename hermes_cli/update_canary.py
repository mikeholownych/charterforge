"""Post-update canary: bounded functional smoke after the code swap.

Runs after ``git pull`` + dependency sync, before the updater hands control
back: a subprocess-isolated import probe of the critical-file set plus a
``hermes --version`` entry-point check. A ``fail`` verdict tells the update
pipeline to roll back to the pre-pull SHA — the same contract as the syntax
guard, one level deeper (imports exercise the cross-module dep graph that a
``py_compile`` parse cannot see).

Known limitation — dep sync after rollback: the canary validates the *code
tree* only. If dependency sync already ran against the pulled tree and the
canary then triggers a rollback, the venv may hold dependencies synced to the
newer ``pyproject.toml`` while the code is at the pre-pull SHA. Correcting
that would require a second dependency sync after rollback (re-running the
editable reinstall), which the rollback path does not currently do.

Default ON via ``updates.post_update_canary``; a skip is explicit and
recorded. Every check is bounded: per-check timeout (``_CHECK_TIMEOUT``) and
a wall-clock budget for the whole canary (``_BUDGET_SECONDS``).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

# In sync with _UPDATE_CRITICAL_FILES in hermes_cli/update_cmd.py — same file
# set, expressed as importable module stems (hermes_cli/__init__.py -> the
# package itself). The syntax guard *parses* those files; we *import* them.
_CORE_IMPORT_PROBES = (
    "hermes_cli",
    "hermes_cli.main",
    "hermes_cli.config",
    "hermes_cli.web_server",
    "cli",
    "run_agent",
    "model_tools",
    "toolsets",
    "hermes_constants",
)

_CHECK_TIMEOUT = 30.0
_BUDGET_SECONDS = 60.0

# Fastest safe smoke for the console entry point (pyproject [project.scripts]:
# hermes = "hermes_cli.main:main"). ``--version`` is a deliberate fast path in
# main.py — handled before config/logging imports — so it does NOT import the
# world (~2s wall, measured). The lighter ``python -c "from hermes_cli.main
# import main"`` alternative only proves one import; this also exercises the
# real ``-m``/argparse dispatch, so it was chosen instead.
_ENTRY_POINT_ARGS = [sys.executable, "-m", "hermes_cli.main", "--version"]


def _last_line(text: str | None) -> str:
    """The last non-empty line of captured output ('' when there is none)."""
    for line in reversed((text or "").splitlines()):
        if line.strip():
            return line.strip()
    return ""


def _run_check(name: str, argv: list[str], cwd, deadline: float) -> dict:
    """Run one bounded subprocess check -> ``{name, ok, detail}``.

    Fails closed: timeout, spawn failure, nonzero exit, and an exhausted
    budget are all ``ok=False`` with the reason in ``detail``.
    """
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return {"name": name, "ok": False, "detail": "skipped: canary budget exhausted"}
    timeout = min(_CHECK_TIMEOUT, remaining)
    try:
        result = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        detail = f"timed out after {timeout:.0f}s"
        partial = _last_line(
            exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout)
        if partial:
            detail += f": {partial}"
        return {"name": name, "ok": False, "detail": detail}
    except OSError as exc:
        return {"name": name, "ok": False, "detail": f"spawn failed: {exc}"}
    if result.returncode != 0:
        tail = _last_line(result.stderr) or _last_line(result.stdout)
        return {
            "name": name,
            "ok": False,
            "detail": f"exit {result.returncode}: {tail or '(no output)'}",
        }
    return {"name": name, "ok": True, "detail": _last_line(result.stdout)}


def _core_imports_check(project_root, python_exe: str, deadline: float) -> dict:
    """One subprocess importing every ``_CORE_IMPORT_PROBES`` entry; the
    combined probe keeps the canary to a single interpreter spin-up."""
    if not _CORE_IMPORT_PROBES:
        return {"name": "core_imports", "ok": True, "detail": "no probes configured"}
    probes_json = json.dumps(list(_CORE_IMPORT_PROBES))
    script = (
        "import json, sys\n"
        f"probes = json.loads({probes_json!r})\n"
        "failures = []\n"
        "for mod in probes:\n"
        "    try:\n"
        "        __import__(mod)\n"
        "    except BaseException as exc:  # any import-time blowup is a canary failure\n"
        "        failures.append([mod, repr(exc)])\n"
        "print(json.dumps(failures))\n"
    )
    result = _run_check(
        "core_imports", [python_exe, "-c", script], project_root, deadline)
    if not result["ok"]:
        return result
    try:
        failures = json.loads(result["detail"] or "[]")
    except ValueError:
        failures = []
    if failures:
        result["ok"] = False
        result["detail"] = "; ".join(f"{mod}: {err}" for mod, err in failures)
    elif not result["detail"]:
        result["detail"] = f"imported {len(_CORE_IMPORT_PROBES)} modules"
    return result


def run_canary(*, project_root, python_exe: str = sys.executable) -> dict:
    """Run the bounded functional smoke; return ``{verdict, checks, duration_seconds}``.

    ``verdict`` is ``"pass"`` only when every check is ok; any failure (or a
    budget-exhausted skip, which fails closed) yields ``"fail"``.
    """
    start = time.monotonic()
    deadline = start + _BUDGET_SECONDS
    checks = [_core_imports_check(project_root, python_exe, deadline)]
    entry_argv = [python_exe, *_ENTRY_POINT_ARGS[1:]]
    checks.append(_run_check("entry_point", entry_argv, project_root, deadline))
    duration = time.monotonic() - start
    verdict = "pass" if all(check["ok"] for check in checks) else "fail"
    return {
        "verdict": verdict,
        "checks": checks,
        "duration_seconds": round(duration, 3),
    }
