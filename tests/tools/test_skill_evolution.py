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
