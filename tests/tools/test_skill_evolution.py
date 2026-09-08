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
    usage_file = home / "skills" / ".usage.json"
    usage_file.write_text(json.dumps({
        "my-skill": {"created_by": "agent", "use_count": 0,
                     "view_count": 0, "patch_count": 0},
    }), encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(home))
    # Fixture is shared across all four task groups: HERMES_HOME pins
    # get_skills_dir() for staging/eval/promotion; the usage record feeds
    # the provenance gate. Task 1's loader takes skill_dir explicitly.
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

    def test_invalid_yaml_raises(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 1\nprompts: [unclosed\n", encoding="utf-8"
        )
        with pytest.raises(EvalManifestError, match="not valid YAML|invalid YAML"):
            load_eval_manifest(agent_skill)

    def test_non_mapping_yaml_raises(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "- just\n- a\n- list\n", encoding="utf-8"
        )
        with pytest.raises(EvalManifestError, match="mapping"):
            load_eval_manifest(agent_skill)

    def test_both_expectations_rejected(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 1\nprompts:\n  - prompt: 'x'\n    expect:\n"
            "      contains: ['step']\n      regex: 'step'\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalManifestError, match="only one of"):
            load_eval_manifest(agent_skill)

    def test_unknown_expect_key_rejected(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 1\nprompts:\n  - prompt: 'x'\n    expect:\n"
            "      contains: ['step']\n      min_score: 0.9\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalManifestError, match="unknown|unsupported"):
            load_eval_manifest(agent_skill)

    def test_duplicate_yaml_keys_rejected(self, agent_skill):
        from agent.skill_evolution import load_eval_manifest, EvalManifestError

        (agent_skill / ".evals.yaml").write_text(
            "version: 1\nprompts:\n  - prompt: 'a'\n    expect:\n"
            "      contains: ['step']\n"
            "prompts:\n  - prompt: 'b'\n    expect:\n      regex: 'x'\n",
            encoding="utf-8",
        )
        with pytest.raises(EvalManifestError, match="duplicate|YAML"):
            load_eval_manifest(agent_skill)

    def test_fixture_comment_and_existing_suite_still_green(self, agent_skill):
        """Existing valid manifest still loads (strict keys don't reject it)."""
        from agent.skill_evolution import load_eval_manifest

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        assert load_eval_manifest(agent_skill)["version"] == 1


class TestCandidateStaging:
    # Premise correction vs the plan sketch: the fixture does NOT monkeypatch
    # config, so every test here pins config_mod.load_config explicitly. With
    # no patch, load_config() reads real config where autonomous_evolution is
    # absent (=> off) and even the happy path would fail G1. Determinism first.

    def test_evolve_stages_candidate_without_touching_live(self, agent_skill, monkeypatch):
        import hermes_cli.config as config_mod
        from tools.skill_manager_tool import skill_manage

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
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
        live = (agent_skill / "SKILL.md").read_text(encoding="utf-8")
        assert "IMPROVED." not in live

    def test_evolve_requires_evolution_enabled(self, agent_skill, monkeypatch):
        import hermes_cli.config as config_mod
        from tools.skill_manager_tool import skill_manage

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": False}},
        )
        result = json.loads(skill_manage(
            "evolve", "my-skill", content="# improved\n",
        ))
        assert result["success"] is False
        assert "autonomous_evolution" in json.dumps(result)

    def test_evolve_refuses_non_agent_skill(self, agent_skill, monkeypatch):
        import hermes_cli.config as config_mod
        from tools.skill_manager_tool import skill_manage

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
        usage_file = agent_skill.parent / ".usage.json"
        usage_file.write_text(json.dumps({
            "my-skill": {"created_by": "human", "use_count": 0,
                         "view_count": 0, "patch_count": 0},
        }), encoding="utf-8")
        result = json.loads(skill_manage(
            "evolve", "my-skill", content="# improved\n",
        ))
        assert result["success"] is False
        assert "created_by" in json.dumps(result)

    def test_evolve_refuses_hub_skill(self, agent_skill, monkeypatch):
        import hermes_cli.config as config_mod
        from tools.skill_manager_tool import skill_manage

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
        hub = agent_skill.parent / "_hub" / "some-bundle"
        hub.mkdir(parents=True)
        (hub / "SKILL.md").write_text("# bundled\n", encoding="utf-8")
        usage_file = agent_skill.parent / ".usage.json"
        usage_file.write_text(json.dumps({
            "some-bundle": {"created_by": "agent", "use_count": 0,
                            "view_count": 0, "patch_count": 0},
        }), encoding="utf-8")
        result = json.loads(skill_manage(
            "evolve", "some-bundle", content="# improved\n",
        ))
        assert result["success"] is False

    def test_evolve_replaces_previous_candidate(self, agent_skill, monkeypatch):
        import hermes_cli.config as config_mod
        from tools.skill_manager_tool import skill_manage

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
        skill_manage("evolve", "my-skill", content="# v1 candidate\n")
        skill_manage("evolve", "my-skill", content="# v2 candidate\n")
        candidate = agent_skill / ".candidate" / "SKILL.md"
        text = candidate.read_text(encoding="utf-8")
        assert "v2" in text and "v1" not in text


class TestEvaluationRunner:
    def test_run_evaluation_passes_on_satisfying_responses(
        self, agent_skill, monkeypatch
    ):
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
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
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

        (agent_skill / ".candidate").mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# CANDIDATE MARKER\n", encoding="utf-8"
        )
        captured.clear()  # second capture replaces the first
        se.run_evaluation(agent_skill)
        assert "CANDIDATE MARKER" in (captured["skills_dir"] / "my-skill" / "SKILL.md").read_text(encoding="utf-8")

    def test_sandbox_excludes_candidate_dir_copy(self, agent_skill, monkeypatch):
        """The .candidate/ dir is copied over SKILL.md, NOT copied as a
        subdirectory — the eval agent must not see two skill bodies."""
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        (agent_skill / ".candidate").mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# CANDIDATE\n", encoding="utf-8"
        )
        seen = {}
        class _SpyAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k): return "steps, verify, retry"
        def spy_build(skills_dir: Path):
            seen["sandbox_skill"] = Path(skills_dir) / agent_skill.name
            return _SpyAgent()
        monkeypatch.setattr(se, "_build_eval_agent", spy_build)
        se.run_evaluation(agent_skill)
        assert not (seen["sandbox_skill"] / ".candidate").exists()
        assert "CANDIDATE" in (seen["sandbox_skill"] / "SKILL.md").read_text(encoding="utf-8")

    def test_missing_manifest_fails_closed(self, agent_skill):
        from agent import skill_evolution as se

        result = se.run_evaluation(agent_skill)
        assert result["verdict"] == "error"
        assert "no .evals.yaml" in result.get("error", "")
        assert result["prompts"] == []

    def test_concurrent_evaluations_get_distinct_sandboxes(
        self, agent_skill, monkeypatch
    ):
        """Two evaluations of the same skill run in distinct sandboxes — no
        shared-state bleed, no process-lifetime cache."""
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        paths = []
        class _SpyAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k): return "steps, verify, retry"
        def spy_build(skills_dir: Path):
            paths.append(Path(skills_dir))
            return _SpyAgent()
        monkeypatch.setattr(se, "_build_eval_agent", spy_build)
        se.run_evaluation(agent_skill)
        se.run_evaluation(agent_skill)
        assert len(paths) == 2 and paths[0] != paths[1]

    def test_agent_build_failure_is_verdict_error(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se

        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        def boom(skills_dir):
            raise RuntimeError("no credentials configured")
        monkeypatch.setattr(se, "_build_eval_agent", boom)
        result = se.run_evaluation(agent_skill)
        assert result["verdict"] == "error"
        assert "no credentials" in result["error"]


class TestPromotion:
    def test_promote_passing_candidate(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        (agent_skill / ".candidate").mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# IMPROVED\n\nstep one, verify output. Retry once.\n",
            encoding="utf-8",
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

    def test_snapshot_failure_aborts_promotion(self, agent_skill, monkeypatch):
        """No backup → no promotion (rollback guarantee)."""
        from agent import skill_evolution as se
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
        (agent_skill / ".evals.yaml").write_text(MANIFEST, encoding="utf-8")
        (agent_skill / ".candidate").mkdir(exist_ok=True)
        (agent_skill / ".candidate" / "SKILL.md").write_text(
            "# IMPROVED\n\nstep one, verify output. Retry once.\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "agent.curator_backup.snapshot_skills",
            lambda reason="manual", **k: (_ for _ in ()).throw(
                OSError("disk full")),
        )
        class _FakeAgent:
            def __init__(self, *a, **k): pass
            def chat(self, message, **k): return "steps, verify, retry once"
        monkeypatch.setattr(se, "_build_eval_agent", lambda skills_dir: _FakeAgent())

        result = se.evaluate_and_promote(agent_skill)
        assert result["promoted"] is False
        assert "snapshot" in json.dumps(result).lower()
        live = (agent_skill / "SKILL.md").read_text(encoding="utf-8")
        assert "IMPROVED" not in live  # untouched
        assert (agent_skill / ".candidate" / "SKILL.md").is_file()  # preserved

    def test_failing_candidate_keeps_incumbent(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
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
        assert (agent_skill / ".candidate" / "SKILL.md").is_file()  # preserved

    def test_promote_refused_when_evolution_disabled(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": False}},
        )
        result = se.evaluate_and_promote(agent_skill)
        assert result["promoted"] is False
        assert "autonomous_evolution" in json.dumps(result)

    def test_promote_refused_non_agent_skill(self, agent_skill, monkeypatch):
        from agent import skill_evolution as se
        import hermes_cli.config as config_mod

        monkeypatch.setattr(
            config_mod, "load_config",
            lambda: {"skills": {"autonomous_evolution": True}},
        )
        (agent_skill.parent / ".usage.json").write_text(json.dumps({
            "my-skill": {"created_by": "human", "use_count": 0,
                         "view_count": 0, "patch_count": 0},
        }), encoding="utf-8")
        result = se.evaluate_and_promote(agent_skill)
        assert result["promoted"] is False
        assert "created_by" in json.dumps(result)
