"""Autonomous skill evolution: eval manifest, candidate staging, isolated
evaluation, controlled promotion. Default OFF; agent-authored skills only."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

SUPPORTED_MANIFEST_VERSION = 1


class EvalManifestError(ValueError):
    """Raised when a skill's .evals.yaml manifest is missing or invalid."""


def load_eval_manifest(skill_dir: str | Path) -> dict:
    """Load and validate a skill's `.evals.yaml` evaluation manifest.

    Returns a normalized dict: {"version": SUPPORTED_MANIFEST_VERSION,
    "prompts": [{"prompt": str, "expect": {"contains": [...]} | {"regex": str}}]}.
    Raises EvalManifestError on absence or invalid schema.
    """
    path = Path(skill_dir) / ".evals.yaml"
    if not path.is_file():
        raise EvalManifestError(f"no .evals.yaml found in {skill_dir}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise EvalManifestError(f".evals.yaml is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise EvalManifestError(".evals.yaml must parse to a mapping")
    version = raw.get("version")
    if version != SUPPORTED_MANIFEST_VERSION:
        raise EvalManifestError(
            f"unsupported manifest version: {version!r} "
            f"(supported: {SUPPORTED_MANIFEST_VERSION})"
        )
    prompts = raw.get("prompts")
    if not isinstance(prompts, list) or not prompts:
        raise EvalManifestError("manifest must include at least one prompt")
    normalized = []
    for index, entry in enumerate(prompts):
        if not isinstance(entry, dict):
            raise EvalManifestError(f"prompt #{index + 1}: each entry must be a mapping")
        prompt = entry.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise EvalManifestError(
                f"prompt #{index + 1}: prompt must be a non-empty string"
            )
        expect = entry.get("expect")
        if not isinstance(expect, dict):
            raise EvalManifestError(f"prompt #{index + 1}: expect must be a mapping")
        contains = expect.get("contains")
        regex = expect.get("regex")
        if contains is not None:
            if (
                not isinstance(contains, list)
                or not contains
                or not all(isinstance(s, str) and s.strip() for s in contains)
            ):
                raise EvalManifestError(
                    f"prompt #{index + 1}: 'contains' must be a non-empty "
                    "list of non-empty strings"
                )
            normalized.append(
                {"prompt": prompt, "expect": {"contains": list(contains)}}
            )
        elif isinstance(regex, str) and regex:
            try:
                re.compile(regex)
            except re.error as exc:
                raise EvalManifestError(
                    f"prompt #{index + 1}: invalid regex: {exc}"
                ) from exc
            normalized.append({"prompt": prompt, "expect": {"regex": regex}})
        else:
            raise EvalManifestError(
                f"prompt #{index + 1}: expect must specify a contains or regex "
                "key (contains: non-empty string list; regex: valid pattern)"
            )
    return {"version": SUPPORTED_MANIFEST_VERSION, "prompts": normalized}
