# Autonomous Skill Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the agent propose skill improvements that are evaluated in isolation against a per-skill eval manifest and promoted only on evidence — with rollback via the existing curator backup — never touching bundled/hub skills or skills without agent provenance.

**Architecture:** Three pieces on existing rails. (1) An eval manifest contract (`.evals.yaml` beside SKILL.md: prompts + checkable expectations) with a loader/validator. (2) Candidate staging: `skill_manage(action="evolve", ...)` writes the improved skill into `<skill>/.candidate/` (never the live dir), gated by `skills.autonomous_evolution` (default false) and `created_by: agent` provenance. (3) An evaluation runner (new `agent/skill_evolution.py`) that materializes a sandbox skills dir containing ONLY the candidate, runs each manifest prompt through a fresh AIAgent (existing class; skills load from `get_skills_dir()` which honors `HERMES_HOME`), checks expectations, and returns a structured verdict. Promotion swaps the candidate into the live skill only after `curator_backup.snapshot_skills()` (rollback); failures keep the incumbent and record evidence. Governance invariants: bundled/hub skills and non-agent-authored skills are refused; the eval agent gets no delegation/web tools; every promotion/discard is auditable via the existing skill_usage sidecar.

**Tech Stack:** Python, PyYAML (already used), AIAgent (existing), curator_backup (existing), pytest via `scripts/run_tests.sh`.

**Files:**
- Create: `agent/skill_evolution.py` (manifest loader/validator + sandbox runner + promote/discard)
- Modify: `tools/skill_manager_tool.py` (`evolve` action → stage candidate)
- Modify: `toolsets.py` (no change expected — skill_manager_tool already registered; verify only)
- Create: `tests/tools/test_skill_evolution.py`
- Modify: `website/docs/guides/agentic-business-os.md` (feature docs)
- Modify: `hermes_cli/config.py` DEFAULT_CONFIG (`skills.autonomous_evolution: false`)

**Governance invariants (non-negotiable):**
1. Default OFF: no eval/evolution activity unless `skills.autonomous_evolution: true`.
2. Provenance gate: only skills whose `.usage.json` record says `created_by: agent` may be staged; bundled/hub/optional skills are refused with a clear error.
3. Candidate isolation: staging NEVER modifies the live SKILL.md; eval runs against a sandbox dir that contains only the candidate.
4. Eval-agent confinement: the eval agent runs with no delegation, no cron, no terminal background, no network write tools — toolset allowlist is explicit in the runner.
5. Promotion requires all manifest expectations to pass; any failure → incumbent kept, verdict + diff recorded, candidate preserved for human review.
6. Rollback: curator_backup snapshot precedes every promotion (pre-existing mechanism).

---

### Task 1: Eval manifest schema + loader

**Files:**
- Create: `agent/skill_evolution.py` (loader/validator portion)
- Test: `tests/tools/test_skill_evolution.py`

- [ ] **Step 1: Failing tests**

```python
"""Autonomous skill evolution: eval manifest, candidate staging, isolated
evaluation, controlled promotion. Default OFF; agent-authored skills only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


MANIFEST = """\
version: 1
prompts:
  - prompt: "Summarize the SKILL.md quick-reference table."
    expect:
      contains: ["step", "verify"]
  - prompt: "What does this skill say about failure handling?"
    expect:
      regex: "(?i)fail|retry|rollback"
"""


@pytest.fixture()
def agent_skill(tmp_path, monkeypatch):
    """A minimal agent-authored skill in a temp HERMES_HOME skills dir."""
    import hermes_constants

    home = tmp_path / "hermes-home"
    skills = home / "skills" / "my-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Test skill.\nversion: 1.0\n"
        'author: "Test <test@example.com>"\ncreated_by: agent\n---\n\n'
        "# My Skill\n\n## Quick Reference\n\nstep one, verify output.\n\n"
        "## Failure Handling\n\nRetry once, then rollback.\n",
        encoding="utf-8",
    )
    from hermes_cli.skill_usage import bump_skill_use  # provenance sidecar

    # Mark agent provenance the way skill_manager_tool does.
    usage_file = home / "skills" / ".usage.json"
    usage_file.write_text(json.dumps({
        "my-skill": {"created_by": "agent", "use_count": 0,
                     "view_count": 0, "patch_count": 0},
    }), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    return skills


class TestManifestLoader:
    def test_loads_and_validates(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        manifest = load_eval_manifest(agent_skill)
        assert manifest["version"] == 1
        assert len(manifest["prompts"]) == 2
        assert manifest["prompts"][0]["expect"]["contains"] == ["step", "verify"]

    def test_missing_manifest_raises(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        with pytest.raises(EvalManifestError, match="no .evals.yaml"):
            load_eval_manifest(agent_skill)

    def test_invalid_schema_raises(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 1\nprompts: []\n", encoding="utf-8"
        )
        with pytest.raises(EvalManifestError, match="at least one prompt"):
            load_eval_manifest(agent_skill)

    def test_expectation_requires_contains_or_regex(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 1\nprompts:\n  - prompt: 'x'\n    expect: {}\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalManifestError, match="contains or regex"):
            load_eval_manifest(agent_skill)

    def test_unknown_version_raises(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 99\nprompts:\n  - prompt: 'x'\n    expect:\n      contains: ['x']\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalManifestError, match="version"):
            load_eval_manifest(agent_skill)
```

(premise check: confirm `created_by` is read from `.usage.json` — skill_manager_tool.py:387-401 says the record lives there; the loader in Task 2 must read the same record, not SKILL.md frontmatter. If the provenance reader already exists as an importable function in skill_usage or skill_manager_tool, reuse it instead of reading the JSON by hand.)

- [ ] **Step 2: RED** — run `scripts/run_tests.sh tests/tools/test_skill_evolution.py -j 1 -q`; record.

- [ ] **Step 3: Implement in `agent/skill_evolution.py`:**

```python
"""Autonomous skill evolution: manifest, staging, isolated evaluation,
promotion with rollback. Default OFF (skills.autonomous_evolution).

Governance: agent-authored skills only (created_by: agent in .usage.json);
candidates never touch the live skill; promotion requires a passing eval
run and is preceded by a curator_backup snapshot.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

SUPPORTED_MANIFEST_VERSION = 1


class EvalManifestError(ValueError):
    """Raised when a skill's .evals.yaml is missing or invalid."""


def load_eval_manifest(skill_dir: Path) -> Dict[str, Any]:
    """Load and validate ``<skill>/.evals.yaml``.

    Schema: {version: 1, prompts: [{prompt: str, expect: {contains: [str]
    | regex: str}}+]}. Raises EvalManifestError with an actionable message
    on any violation.
    """
    path = skill_dir / ".evals.yaml"
    if not path.is_file():
        raise EvalManifestError(f"no .evals.yaml in {skill_dir}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EvalManifestError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvalManifestError(f"{path} must be a mapping")
    if raw.get("version") != SUPPORTED_MANIFEST_VERSION:
        raise EvalManifestError(
            f"{path}: unsupported manifest version "
            f"{raw.get('version')!r} (supported: {SUPPORTED_MANIFEST_VERSION})"
        )
    prompts = raw.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise EvalManifestError(f"{path}: prompts must list at least one prompt")
    normalized: List[Dict[str, Any]] = []
    for i, entry in enumerate(prompts):
        if not isinstance(entry, dict) or not str(entry.get("prompt", "")).strip():
            raise EvalManifestError(f"{path}: prompts[{i}].prompt must be a non-empty string")
        expect = entry.get("expect")
        if not isinstance(expect, dict):
            raise EvalManifestError(f"{path}: prompts[{i}].expect must be a mapping")
        contains = expect.get("contains")
        regex = expect.get("regex")
        if not contains and not regex:
            raise EvalManifestError(
                f"{path}: prompts[{i}].expect must declare contains or regex"
            )
        if contains is not None:
            if not isinstance(contains, list) or not all(
                isinstance(c, str) and c for c in contains
            ):
                raise EvalManifestError(
                    f"{path}: prompts[{i}].expect.contains must be a list of non-empty strings"
                )
        if regex is not None:
            try:
                re.compile(regex)
            except re.error as exc:
                raise EvalManifestError(
                    f"{path}: prompts[{i}].expect.regex invalid: {exc}"
                ) from exc
        normalized.append({"prompt": str(entry["prompt"]), "expect": expect})
    return {"version": SUPPORTED_MANIFEST_VERSION, "prompts": normalized}
```

- [ ] **Step 4: GREEN** — expect 5 passed.
- [ ] **Step 5: Commit** — `feat(skills): eval manifest schema + loader (skill evolution 1/4)`

---

### Task 2: Candidate staging via skill_manage `evolve` action

**Files:**
- Modify: `tools/skill_manager_tool.py`
- Test: `tests/tools/test_skill_evolution.py`

- [ ] **Step 1: Failing tests**

```python
class TestCandidateStaging:
    def test_evolve_stages_candidate_without_touching_live(self, agent_skill):
        from tools.skill_manager_tool import skill_manage

        improved = ("---\nname: my-skill\ndescription: Test skill.\n"
                    "version: 1.1\nauthor: \"Test <test@example.com>\"\n"
                    "created_by: agent\n---\n\n# My Skill\n\nIMPROVED.\n")
        result = json.loads(skill_manage(
            "evolve", "my-skill", content=improved,
        ))
        assert result["success"] is True
        candidate = agent_skill / ".candidate" / "SKILL.md"
        assert candidate.is_file()
        assert "IMPROVED." in candidate.read_text(encoding="utf-8")
        # Live untouched:
        assert "IMPROVED." not in (agent_skill / "SKILL.md").read_text(encoding="utf-8")

    def test_evolve_requires_evolution_enabled(self, agent_skill, monkeypatch):
        from tools.skill_manager_tool import skill_manage

        monkeypatch.setenv("SKILLS_AUTONOMOUS_EVOLUTION", "")  # default off
        result = json.loads(skill_manage(
            "evolve", "my-skill", content="# improved\n",
        ))
        assert result["success"] is False
        assert "autonomous_evolution" in json.dumps(result)

    def test_evolve_refuses_non_agent_skill(self, agent_skill, monkeypatch):
        """created_by != agent (or missing record) → refused."""
        import json as _json
        from tools.skill_manager_tool import skill_manage

        usage_file = agent_skill.parent / ".usage.json"
        usage_file.write_text(_json.dumps({
            "my-skill": {"created_by": "human", "use_count": 0,
                         "view_count": 0, "patch_count": 0},
        }), encoding="utf-8")
        result = json.loads(skill_manage(
            "evolve", "my-skill", content="# improved\n",
        ))
        assert result["success"] is False
        assert "created_by" in json.dumps(result)

    def test_evolve_refuses_bundled_or_hub_skills(self, agent_skill, monkeypatch):
        """A skill under a hub/bundled namespace (e.g. _hub/) is refused even
        if a usage record claims agent authorship."""
        from tools.skill_manager_tool import skill_manage

        hub_skill = agent_skill.parent / "_hub" / "some-bundle"
        hub_skill.mkdir(parents=True)
        (hub_skill / "SKILL.md").write_text("# bundled\n", encoding="utf-8")
        usage_file = agent_skill.parent / ".usage.json"
        usage_file.write_text(json.dumps({
            "some-bundle": {"created_by": "agent", "use_count": 0,
                            "view_count": 0, "patch_count": 0},
        }), encoding="utf-8")
        result = json.loads(skill_manage(
            "evolve", "some-bundle", content="# improved\n",
        ))
        assert result["success"] is False

    def test_evolve_replaces_previous_candidate(self, agent_skill):
        from tools.skill_manager_tool import skill_manage

        skill_manage("evolve", "my-skill", content="# v1 candidate\n")
        skill_manage("evolve", "my-skill", content="# v2 candidate\n")
        candidate = agent_skill / ".candidate" / "SKILL.md"
        assert "v2" in candidate.read_text(encoding="utf-8")
        assert "v1" not in candidate.read_text(encoding="utf-8")
```

Config gate note for the implementer: read the gate via the existing config path — `hermes_cli.config.load_config()` → `skills.autonomous_evolution` (add `autonomous_evolution: False` under `skills:` in DEFAULT_CONFIG in hermes_cli/config.py, plus config-version policy per AGENTS.md: adding a key under an existing section does NOT require a version bump). The env-var test shim above may need to become a monkeypatched `load_config` instead — adapt to whatever pattern the file already uses for config reads; do NOT add a new `HERMES_*` env var (AGENTS.md policy: config.yaml only).

- [ ] **Step 2: RED** — record.
- [ ] **Step 3: Implement in `tools/skill_manager_tool.py`:**

New action handler `_evolve_skill(name, content)`:
- Gate 1: `skills.autonomous_evolution` must be true (else tool_error naming the config key).
- Gate 2: resolve the skill dir via the same lookup `_edit_skill` uses; REFUSE if the resolved path is under `_hub/`, `optional-skills/`, or is a bundled skill (reuse any existing bundled/hub detection in the file; if none exists, refuse when the path is not directly under `get_skills_dir()`).
- Gate 3: provenance — read the skill's `.usage.json` record (reuse the existing reader at skill_manager_tool.py:387-401's logic or import it) and require `created_by == "agent"`.
- Write candidate: `<skill_dir>/.candidate/SKILL.md` (mkdir -p; overwrite prior candidate).
- Update `.usage.json` patch_count? NO — staging is not a patch. Record a dedicated sidecar note is unnecessary; the candidate dir IS the durable record.
- Return `{"success": True, "staged": True, "candidate": str(path), "next": "run skill evolution evaluation"}`.

Wire `elif action == "evolve":` into `skill_manage` (before the generic create/edit dispatch, after the write-gate call so the approval gate does NOT intercept evolve — evolution has its own gates; document this in a comment).

- [ ] **Step 4: GREEN** — expect all prior + 5 new = 10 passed (Task 1's 5 + these 5).
- [ ] **Step 5: Regression** — `scripts/run_tests.sh tests/tools/test_skill_manager_tool.py tests/tools/test_skills_tool.py -j 2 -q`; record (report unrelated failures separately).
- [ ] **Step 6: Commit** — `feat(skills): evolve action stages candidates (governed, default off)`

---

### Task 3: Isolated evaluation runner

**Files:**
- Modify: `agent/skill_evolution.py`
- Test: `tests/tools/test_skill_evolution.py`

- [ ] **Step 1: Failing tests**

```python
class TestEvaluationRunner:
    def test_run_evaluation_passes_on_satisfying_responses(
        self, agent_skill, monkeypatch
    ):
        """Fake the AIAgent seam; responses satisfy the manifest."""
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")

        class _FakeAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k):
                return "Follow the steps and verify the output. Retry once."

        monkeypatch.setattr(se, "_build_eval_agent", lambda skills_dir: _FakeAgent())
        result = se.run_evaluation(agent_skill)
        assert result["verdict"] == "pass"
        assert all(p["passed"] for p in result["prompts"])
        assert result["manifest_version"] == 1

    def test_run_evaluation_fails_on_unsatisfying_response(
        self, agent_skill, monkeypatch
    ):
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")

        class _BadAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k):
                return "I have no idea what you mean."

        monkeypatch.setattr(se, "_build_eval_agent", lambda skills_dir: _BadAgent())
        result = se.run_evaluation(agent_skill)
        assert result["verdict"] == "fail"
        assert any(not p["passed"] for p in result["prompts"])

    def test_sandbox_contains_only_candidate(self, agent_skill, monkeypatch):
        """The eval agent's skills dir must contain ONLY the candidate —
        captured via the _build_eval_agent seam argument."""
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        # Another skill lives in the real dir; it must NOT be in the sandbox.
        other = agent_skill.parent / "other-skill"
        other.mkdir()
        (other / "SKILL.md").write_text("# other\n", encoding="utf-8")

        captured = {}
        class _SpyAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k):
                return "steps, verify, retry"

        def spy_build(skills_dir: Path):
            captured["skills_dir"] = Path(skills_dir)
            return _SpyAgent()

        monkeypatch.setattr(se, "_build_eval_agent", spy_build)
        se.run_evaluation(agent_skill)
        sandbox = captured["skills_dir"]
        names = {p.name for p in sandbox.iterdir()}
        assert "other-skill" not in names
        assert "my-skill" in names
        # The sandboxed skill is the CANDIDATE content:
        sandbox_skill = sandbox / "my-skill" / "SKILL.md"
        # No candidate staged yet → sandbox uses the live skill; with a
        # candidate staged, the candidate content is what's evaluated.
        (agent_skill / ".candidate").mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# CANDIDATE MARKER\n", encoding="utf-8"
        )
        se.run_evaluation(agent_skill)
        assert "CANDIDATE MARKER" in (sandbox / "my-skill" / "SKILL.md").read_text(encoding="utf-8")

    def test_missing_manifest_fails_closed(self, agent_skill):
        from agent import skill_evolution as se

        result = se.run_evaluation(agent_skill)
        assert result["verdict"] == "error"
        assert "no .evals.yaml" in result.get("error", "")
```

- [ ] **Step 2: RED** — record.
- [ ] **Step 3: Implement in `agent/skill_evolution.py`:**

```python
def _build_eval_agent(skills_dir: Path):
    """A fresh AIAgent confined to the sandbox skills dir with a minimal
    toolset (no delegation/cron/terminal-background/network-write).

    The eval agent exists ONLY to answer manifest prompts as the skill
    instructs — it is not an autonomous actor.
    """
    from run_agent import AIAgent

    return AIAgent(
        enabled_toolsets=["skills", "file", "clarify"],
        disabled_toolsets=["delegation", "cronjob", "terminal", "browser",
                           "web", "code_execution", "messaging"],
        skip_context_files=True,
        skip_memory=True,
        quiet_mode=True,
    )


def _check_expectation(response: str, expect: Dict[str, Any]) -> bool:
    if not str(response or "").strip():
        return False
    contains = expect.get("contains")
    if contains and not all(c.lower() in response.lower() for c in contains):
        return False
    regex = expect.get("regex")
    if regex and not re.search(regex, response):
        return False
    return True


def run_evaluation(skill_dir: Path, *, max_turns: int = 4) -> Dict[str, Any]:
    """Evaluate the candidate (or live) skill against its .evals.yaml in an
    isolated sandbox. Returns {verdict: pass|fail|error, prompts: [...],
    sandbox, manifest_version?, error?}."""
    import shutil
    import tempfile

    from hermes_constants import get_skills_dir

    try:
        manifest = load_eval_manifest(skill_dir)
    except EvalManifestError as exc:
        return {"verdict": "error", "error": str(exc), "prompts": []}

    candidate = skill_dir / ".candidate" / "SKILL.md"
    source = candidate if candidate.is_file() else skill_dir / "SKILL.md"

    with tempfile.TemporaryDirectory(prefix="skill-eval-") as tmp:
        sandbox = Path(tmp) / "skills"
        sandbox.mkdir()
        shutil.copytree(skill_dir, sandbox / skill_dir.name,
                        ignore=shutil.ignore_patterns(".candidate", ".curator_backups"))
        if candidate.is_file():
            shutil.copy2(candidate, sandbox / skill_dir.name / "SKILL.md")

        agent = _build_eval_agent(sandbox)
        results = []
        for entry in manifest["prompts"]:
            try:
                response = agent.chat(entry["prompt"])
            except Exception as exc:
                results.append({"prompt": entry["prompt"], "passed": False,
                                "error": f"{type(exc).__name__}: {exc}",
                                "response": ""})
                continue
            results.append({
                "prompt": entry["prompt"],
                "passed": _check_expectation(response, entry["expect"]),
                "response": str(response)[:2000],
            })
    passed_all = bool(results) and all(r["passed"] for r in results)
    return {"verdict": "pass" if passed_all else "fail",
            "prompts": results, "manifest_version": manifest["version"]}

```

NOTE for the implementer: `_build_eval_agent` with the real AIAgent may be too heavyweight/fragile for unit tests — that's why tests monkeypatch the seam. The REAL agent path must still be implemented correctly (AIAgent kwargs above are a best-effort sketch — read AIAgent.__init__'s real signature in run_agent.py:9258ff and adapt; if some kwargs don't exist, drop them and note). The harness's real-agent path gets exercised in Task 4's smoke, not unit tests.

- [ ] **Step 4: GREEN** — expect 14 passed (10 + 4).
- [ ] **Step 5: Regression** — policy + skill suites.
- [ ] **Step 6: Commit** — `feat(skills): isolated evaluation runner for skill candidates`

---

### Task 4: Promotion + rollback + CLI/agent surface

**Files:**
- Modify: `agent/skill_evolution.py`
- Test: `tests/tools/test_skill_evolution.py`

- [ ] **Step 1: Failing tests**

```python
class TestPromotion:
    def test_promote_passing_candidate(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        (agent_skill / ".candidate" / "SKILL.md").parent.mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# IMPROVED\n", encoding="utf-8"
        )

        snapshots = []
        monkeypatch.setattr(
            "agent.curator_backup.snapshot_skills",
            lambda reason="manual", **k: snapshots.append(reason) or Path("/tmp/fake.tgz"),
        )
        class _FakeAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k): return "steps, verify, retry once"
        monkeypatch.setattr(se, "_build_eval_agent", lambda skills_dir: _FakeAgent())

        result = se.evaluate_and_promote(agent_skill)
        assert result["verdict"] == "pass"
        assert result["promoted"] is True
        assert "IMPROVED" in (agent_skill / "SKILL.md").read_text(encoding="utf-8")
        assert snapshots == ["skill_evolution"]  # backup BEFORE swap
        assert not (agent_skill / ".candidate").exists()  # consumed

    def test_failing_candidate_keeps_incumbent(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        (agent_skill / ".candidate").mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# BROKEN candidate — no manifest keywords\n", encoding="utf-8"
        )
        class _BadAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k): return "no idea"
        monkeypatch.setattr(se, "_build_eval_agent", lambda skills_dir: _BadAgent())

        result = se.evaluate_and_promote(agent_skill)
        assert result["verdict"] == "fail"
        assert result["promoted"] is False
        live = (agent_skill / "SKILL.md").read_text(encoding="utf-8")
        assert "BROKEN" not in live
        assert "IMPROVED" not in live
        assert (agent_skill / ".candidate" / "SKILL.md").is_file()  # preserved

    def test_promote_refused_when_evolution_disabled(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se
        from hermes_cli import config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config", lambda: {"skills": {"autonomous_evolution": False}}
        )
        result = se.evaluate_and_promote(agent_skill)
        assert result["promoted"] is False
        assert "autonomous_evolution" in json.dumps(result)
```

- [ ] **Step 2: RED** — record.
- [ ] **Step 3: Implement `evaluate_and_promote(skill_dir)` in `agent/skill_evolution.py`:**
- Gate: config `skills.autonomous_evolution` true (read via hermes_cli.config.load_config; false → `{"promoted": False, "reason": "...autonomous_evolution..."}`).
- Provenance gate (same as Task 2).
- `run_evaluation` → verdict.
- pass → `agent.curator_backup.snapshot_skills(reason="skill_evolution")` FIRST, then copy `.candidate/SKILL.md` → live `SKILL.md`, remove `.candidate/`, return promoted=True with the eval result embedded.
- fail/error → return verdict + promoted=False (candidate preserved).
- All steps wrapped so an exception mid-promotion leaves the live skill untouched (copy to temp then atomic replace within the skill dir).

- [ ] **Step 4: GREEN** — expect 17 passed.
- [ ] **Step 5: Commit** — `feat(skills): evaluate-and-promote with curator rollback`

---

### Task 5: Config key + docs

**Files:**
- Modify: `hermes_cli/config.py` (DEFAULT_CONFIG `skills.autonomous_evolution: False`)
- Modify: `website/docs/guides/agentic-business-os.md`

- [ ] **Step 1:** Add `autonomous_evolution: False` under the `skills:` section in DEFAULT_CONFIG (no version bump — new key under existing section).
- [ ] **Step 2:** Run `scripts/run_tests.sh tests/hermes_cli/test_config.py -j 1 -q` → all pass.
- [ ] **Step 3:** Guide section "## Skill evolution": manifest contract, staging, sandboxed eval, promotion/rollback, governance boundaries (agent-authored only, default off, eval-agent confinement).
- [ ] **Step 4:** Commit — `docs+config: skill evolution gate + guide`
- [ ] **Step 5: Final feature regression** — full test file + skill suites + objective family; record counts; final review subagent verdict; push.

Self-review note: AIAgent's real kwargs need verification in Task 3 (the sketch may not match run_agent.py's current __init__ — the implementer MUST read the real signature and adapt; if the real agent is impractical in-sandbox, the seam stays monkeypatched in tests and the real path is smoke-tested manually, documented honestly). The manifest is intentionally read-only text checks for slice 1; command-based expectations (verify: cmd) are a follow-up — do NOT add them now (YAGNI + shell-exec in eval is a security surface requiring its own design).
