"""Autonomous skill evolution: eval manifest, candidate staging, isolated
evaluation, controlled promotion. Default OFF; agent-authored skills only."""
from __future__ import annotations

import re
from collections.abc import Hashable
from pathlib import Path

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
