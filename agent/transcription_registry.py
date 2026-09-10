"""
Transcription Provider Registry
================================

Central map of registered STT providers. Populated by plugins at
import-time via :meth:`PluginContext.register_transcription_provider`;
consumed by :mod:`tools.transcription_tools` to dispatch
:func:`transcribe_audio` calls to the active plugin backend **when**
the configured ``stt.provider`` name is not a built-in.

Built-ins-always-win
--------------------
Plugin names that collide with a built-in STT provider (``local``,
``local_command``, ``groq``, ``openai``, ``mistral``, ``xai``) are
rejected at registration with a warning. This invariant is also
re-checked at dispatch time in
:func:`tools.transcription_tools._dispatch_to_plugin_provider`.

Scoped registration (per-profile multiplexed gateways) and the plugin
snapshot/restore contract live in the shared
:class:`agent.provider_registry.ProviderRegistry` engine; its bound methods
are re-exported here under the historical module-level names.
"""

from __future__ import annotations

import logging

from agent.provider_registry import ProviderRegistry, lower_key
from agent.transcription_provider import TranscriptionProvider

logger = logging.getLogger(__name__)


# Names reserved for native built-in STT handlers. Plugins cannot
# register a name in this set — the registration call is rejected with
# a warning. **Kept in sync with ``BUILTIN_STT_PROVIDERS`` in
# :mod:`tools.transcription_tools`** — a regression test in
# ``tests/agent/test_transcription_registry.py::TestBuiltinSync``
# fails if the two lists drift. Importing from
# ``tools.transcription_tools`` directly would create a circular
# dependency (``tools.transcription_tools`` imports
# ``agent.transcription_registry`` for dispatch).
_BUILTIN_NAMES = frozenset({
    "local",
    "local_command",
    "groq",
    "openai",
    "mistral",
    "xai",
    "elevenlabs",
    "deepinfra",
})


def _warn_builtin_collision(key: str) -> None:
    logger.warning(
        "Transcription provider '%s' shadows a built-in name; registration "
        "ignored. Built-in STT providers (%s) always win — pick a different "
        "name.",
        key, ", ".join(sorted(_BUILTIN_NAMES)),
    )


_registry: ProviderRegistry[TranscriptionProvider] = ProviderRegistry(
    label="Transcription",
    provider_cls=TranscriptionProvider,
    logger=logger,
    normalize=lower_key,
    builtin_names=_BUILTIN_NAMES,
    on_builtin_collision=_warn_builtin_collision,
)
_registry.export(globals())
