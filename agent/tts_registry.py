"""
TTS Provider Registry
=====================

Central map of registered TTS providers. Populated by plugins at
import-time via :meth:`PluginContext.register_tts_provider`; consumed by
:mod:`tools.tts_tool` to dispatch ``tts_speak`` / ``tts_generate`` calls to
the active plugin backend **when** the configured ``tts.provider`` name is
not a built-in.

Built-ins-always-win
--------------------
Plugin names that collide with a built-in TTS provider are rejected at
registration with a warning.

Scoped registration (per-profile multiplexed gateways) and the plugin
snapshot/restore contract live in the shared
:class:`agent.provider_registry.ProviderRegistry` engine; its bound methods
are re-exported here under the historical module-level names.
"""

from __future__ import annotations

import logging

from agent.provider_registry import ProviderRegistry, lower_key
from agent.tts_provider import TTSProvider

logger = logging.getLogger(__name__)


# Names reserved for native built-in TTS handlers. Plugins cannot
# register a name in this set — the registration call is rejected with
# a warning. **Kept in sync with ``BUILTIN_TTS_PROVIDERS`` in
# :mod:`tools.tts_tool`** — a regression test in
# ``tests/agent/test_tts_registry.py::TestBuiltinSync`` fails if the
# two lists drift. Importing from ``tools.tts_tool`` directly would
# create a circular dependency (``tools.tts_tool`` imports
# ``agent.tts_registry`` for dispatch).
_BUILTIN_NAMES = frozenset({
    "edge",
    "elevenlabs",
    "openai",
    "minimax",
    "xai",
    "mistral",
    "gemini",
    "neutts",
    "kittentts",
    "piper",
    "deepinfra",
})


def _warn_builtin_collision(key: str) -> None:
    logger.warning(
        "TTS provider '%s' shadows a built-in name; registration ignored. "
        "Built-in TTS providers (%s) always win — pick a different name.",
        key, ", ".join(sorted(_BUILTIN_NAMES)),
    )


_registry: ProviderRegistry[TTSProvider] = ProviderRegistry(
    label="TTS",
    provider_cls=TTSProvider,
    logger=logger,
    normalize=lower_key,
    builtin_names=_BUILTIN_NAMES,
    on_builtin_collision=_warn_builtin_collision,
)
_registry.export(globals())
