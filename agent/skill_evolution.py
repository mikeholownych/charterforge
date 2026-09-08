"""Autonomous skill evolution: eval manifest, candidate staging, isolated
evaluation, controlled promotion. Default OFF; agent-authored skills only."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from collections.abc import Hashable
from pathlib import Path
from typing import Any, Dict

import yaml

SUPPORTED_MANIFEST_VERSION = 1
_ALLOWED_EXPECT_KEYS = frozenset({"contains", "regex"})


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys: a silently last-win
    duplicate can weaken an eval gate without a trace."""


def _no_duplicates(loader, node, deep=False):
    if isinstance(node, yaml.MappingNode):
        loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, Hashable):
            raise yaml.YAMLError(f"unhashable key {key!r} in eval manifest")
        if key in mapping:
            raise yaml.YAMLError(f"duplicate key {key!r} in eval manifest")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates
)


class EvalManifestError(ValueError):
    """Raised when a skill's .evals.yaml manifest is missing or invalid."""


def _err(path: Path, msg: str) -> str:
    """Prefix eval-manifest errors with the manifest path for attribution."""
    return f"{path}: {msg}"


def load_eval_manifest(skill_dir: str | Path) -> dict:
    """Load and validate a skill's `.evals.yaml` evaluation manifest.

    Returns a normalized dict: {"version": SUPPORTED_MANIFEST_VERSION,
    "prompts": [{"prompt": str, "expect": {"contains": [...]} | {"regex": str}}]}.
    Raises EvalManifestError on absence or invalid schema.
    """
    path = Path(skill_dir) / ".evals.yaml"
    if not path.is_file():
        raise EvalManifestError(_err(path, "no .evals.yaml found"))
    # Top-level manifest keys stay lenient for now (only version + prompts are
    # checked); strict top-level key rejection lands with future schema needs.
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise EvalManifestError(_err(path, f"not valid YAML: {exc}")) from exc
    if not isinstance(raw, dict):
        raise EvalManifestError(_err(path, "manifest must parse to a mapping"))
    version = raw.get("version")
    if version != SUPPORTED_MANIFEST_VERSION:
        raise EvalManifestError(
            _err(
                path,
                f"unsupported manifest version: {version!r} "
                f"(supported: {SUPPORTED_MANIFEST_VERSION})",
            )
        )
    prompts = raw.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise EvalManifestError(_err(path, "manifest must include at least one prompt"))
    normalized = []
    for index, entry in enumerate(prompts):
        if not isinstance(entry, dict):
            raise EvalManifestError(
                _err(path, f"prompt #{index + 1}: each entry must be a mapping")
            )
        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise EvalManifestError(
                _err(path, f"prompt #{index + 1}: prompt must be a non-empty string")
            )
        expect = entry.get("expect")
        if not isinstance(expect, dict):
            raise EvalManifestError(
                _err(path, f"prompt #{index + 1}: expect must be a mapping")
            )
        unknown_keys = sorted(
            (key for key in expect if key not in _ALLOWED_EXPECT_KEYS), key=repr
        )
        if unknown_keys:
            raise EvalManifestError(
                _err(
                    path,
                    f"prompt #{index + 1}: unsupported expect key(s): "
                    + ", ".join(repr(k) for k in unknown_keys)
                    + "; only one of 'contains' (non-empty string list) or "
                    "'regex' (valid pattern) is allowed",
                )
            )
        contains = expect.get("contains")
        regex = expect.get("regex")
        if contains is not None and regex is not None:
            raise EvalManifestError(
                _err(
                    path,
                    f"prompt #{index + 1}: only one of 'contains' or 'regex' may "
                    "be declared per expect block",
                )
            )
        if contains is not None:
            if (
                not isinstance(contains, list)
                or not contains
                or not all(isinstance(s, str) and s.strip() for s in contains)
            ):
                raise EvalManifestError(
                    _err(
                        path,
                        f"prompt #{index + 1}: 'contains' must be a non-empty "
                        "list of non-empty strings",
                    )
                )
            normalized.append(
                {"prompt": prompt, "expect": {"contains": list(contains)}}
            )
        elif isinstance(regex, str) and regex:
            try:
                re.compile(regex)
            except re.error as exc:
                raise EvalManifestError(
                    _err(path, f"prompt #{index + 1}: invalid regex: {exc}")
                ) from exc
            normalized.append({"prompt": prompt, "expect": {"regex": regex}})
        else:
            raise EvalManifestError(
                _err(
                    path,
                    f"prompt #{index + 1}: expect must specify a contains or regex "
                    "key (contains: non-empty string list; regex: valid pattern)",
                )
            )
    return {"version": SUPPORTED_MANIFEST_VERSION, "prompts": normalized}


def _build_eval_agent(skills_dir: Path):
    """Build a confined AIAgent whose skills root is the eval sandbox.

    Confinement contract: strict allowlist via ``enabled_toolsets`` (the
    safer real-world form — any toolset added later is automatically
    excluded, so no maintenance against a blocklist). delegation, cronjob,
    terminal, browser, web, code_execution and all messaging toolsets are
    thereby unreachable. Missing credentials are tolerated at construction;
    a credential failure surfaces per-prompt as a failed entry; any
    construction exception is converted to an error verdict by
    run_evaluation.
    """
    from run_agent import AIAgent

    return AIAgent(
        enabled_toolsets=["skills", "file", "clarify"],
        skip_context_files=True,
        skip_memory=True,
        quiet_mode=True,
    )


def _check_expectation(response: Any, expect: dict) -> bool:
    """Non-empty response AND every contains substring present (case
    insensitive) AND (for regex manifests) the pattern matches."""
    if not isinstance(response, str) or not response.strip():
        return False
    contains = expect.get("contains")
    if contains is not None:
        lowered = response.lower()
        return all(str(sub).lower() in lowered for sub in contains)
    regex = expect.get("regex")
    if isinstance(regex, str) and regex:
        try:
            return re.search(regex, response) is not None
        except re.error as exc:
            raise EvalManifestError(f"invalid expect regex: {exc}") from exc
    return False


def run_evaluation(skill_dir: str | Path) -> Dict[str, Any]:
    """Evaluate a skill candidate against its .evals.yaml manifest.

    Runs a confined agent inside a sandbox containing ONLY the candidate
    skill (the .candidate overlay is what gets evaluated) and returns
    {"verdict": "pass"|"fail"|"error", "prompts": [...], "manifest_version": 1}.
    Prompt failures surface on the prompt record, never as raised exceptions.
    The sandbox is a fresh temporary directory created per call — no
    per-skill cache or shared state — so concurrent evaluations of the same
    skill never collide, and no evaluation reuses another's directory.
    """
    skill_dir = Path(skill_dir)
    try:
        manifest = load_eval_manifest(skill_dir)
    except EvalManifestError as exc:
        return {"verdict": "error", "error": str(exc), "prompts": []}

    sandbox_root = Path(tempfile.mkdtemp(prefix="hermes-skill-eval-"))
    sandbox_skill = sandbox_root / skill_dir.name
    shutil.copytree(
        skill_dir,
        sandbox_skill,
        ignore=shutil.ignore_patterns(
            ".candidate", ".curator_backups", "__pycache__"
        ),
    )
    candidate = skill_dir / ".candidate" / "SKILL.md"
    if candidate.is_file():
        shutil.copyfile(candidate, sandbox_skill / "SKILL.md")

    try:
        agent = _build_eval_agent(sandbox_root)
    except Exception as exc:
        return {"verdict": "error", "error": str(exc), "prompts": []}

    prompt_results = []
    for entry in manifest["prompts"]:
        prompt_text = entry["prompt"]
        expect = entry["expect"]
        try:
            response = agent.chat(prompt_text)
        except Exception as exc:
            prompt_results.append({
                "prompt": prompt_text,
                "passed": False,
                "response": None,
                "error": str(exc),
            })
            continue
        prompt_results.append({
            "prompt": prompt_text,
            "response": response,
            "error": None,
            "passed": _check_expectation(response, expect),
        })
    verdict = (
        "pass" if prompt_results and all(p["passed"] for p in prompt_results)
        else "fail"
    )
    return {
        "verdict": verdict,
        "prompts": prompt_results,
        "manifest_version": manifest.get("version", 1),
    }


def evaluate_and_promote(skill_dir: str | Path) -> Dict[str, Any]:
    """Run the full evolution cycle for one skill: gates → evaluate the
    staged candidate → snapshot for rollback → atomically promote.

    Governance gates, in order:
      G1 ``skills.autonomous_evolution`` must be enabled (default off).
      G2 the skill must be a top-level user skill under ``get_skills_dir()``
         (never bundled/hub/backup/hidden namespaces) and ``skill_dir`` must
         resolve to exactly that directory.
      G3 the ``.usage.json`` provenance marker must be ``created_by: "agent"``.

    On a "pass" verdict, a curator backup snapshot is taken BEFORE any
    mutation — if the snapshot fails, promotion is aborted (never promote
    without a rollback path). The swap itself is atomic: the candidate is
    copied to a staging file inside the skill directory and ``os.replace``d
    over the live SKILL.md, so a mid-swap failure leaves the incumbent
    untouched. The staged candidate is consumed (rmtree) only after a
    successful replace. On "fail"/"error" verdicts the incumbent and the
    candidate are both preserved.
    """
    skill_dir = Path(skill_dir)

    # Deferred imports: tools.* may import heavy deps (and agent -> tools at
    # module scope would invert the layering); the call-time import also keeps
    # the gates patchable from tests.
    from tools.skill_manager_tool import (
        _evolution_enabled,
        _evolution_skill_dir,
        _skill_created_by,
    )

    # G1: feature gate (fail closed).
    if not _evolution_enabled():
        return {
            "promoted": False,
            "verdict": "error",
            "prompts": [],
            "error": (
                "autonomous skill evolution is disabled "
                "(set skills.autonomous_evolution: true in config.yaml)"
            ),
        }

    # G2: top-level user skill + path identity.
    gate_dir = _evolution_skill_dir(skill_dir.name)
    if gate_dir is None or gate_dir.resolve() != skill_dir.resolve():
        return {
            "promoted": False,
            "verdict": "error",
            "prompts": [],
            "error": (
                f"{skill_dir}: not a top-level user skill directory (G2)"
            ),
        }

    # G3: provenance.
    if _skill_created_by(skill_dir.name) != "agent":
        return {
            "promoted": False,
            "verdict": "error",
            "prompts": [],
            "error": (
                f"{skill_dir.name}: .usage.json created_by is not 'agent' (G3)"
            ),
        }

    # Evaluate the CANDIDATE (run_evaluation prefers .candidate/SKILL.md).
    result = run_evaluation(skill_dir)
    verdict = result.get("verdict")
    if verdict != "pass":
        # Candidate preserved, incumbent untouched.
        return {"promoted": False, **result}

    candidate = skill_dir / ".candidate" / "SKILL.md"
    if not candidate.is_file():
        return {
            "promoted": False,
            "verdict": "pass",
            "prompts": result.get("prompts", []),
            "manifest_version": result.get("manifest_version"),
            "error": (
                f"{skill_dir}: eval passed but no staged candidate "
                "SKILL.md found to promote"
            ),
        }

    # Rollback snapshot BEFORE any mutation — never promote without a backup.
    from agent.curator_backup import snapshot_skills

    def _snapshot_failure(exc: str) -> Dict[str, Any]:
        return {
            "promoted": False,
            "verdict": "pass",
            "prompts": result.get("prompts", []),
            "manifest_version": result.get("manifest_version"),
            "error": (
                f"rollback snapshot failed; promotion aborted: {exc}"
            ),
        }

    try:
        snapshot = snapshot_skills(reason="skill_evolution")
    except Exception as exc:
        return _snapshot_failure(str(exc))
    if snapshot is None:
        return _snapshot_failure("snapshot_skills returned None")

    # Atomic swap: copy candidate to a staging file on the same filesystem,
    # then os.replace over the live SKILL.md. A failure before the replace
    # leaves the incumbent untouched.
    staging = skill_dir / ".SKILL.md.evolving"
    try:
        shutil.copy2(candidate, staging)
        os.replace(staging, skill_dir / "SKILL.md")
    except OSError as exc:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass
        return {
            "promoted": False,
            "verdict": "pass",
            "prompts": result.get("prompts", []),
            "manifest_version": result.get("manifest_version"),
            "error": f"atomic swap failed; live skill untouched: {exc}",
        }

    # Promotion succeeded — consume the staged candidate (best-effort; the
    # live skill is already replaced, so a rmtree failure must not un-promote).
    try:
        shutil.rmtree(skill_dir / ".candidate")
    except OSError:
        pass

    return {"promoted": True, "snapshot": str(snapshot), **result}
