"""Specialist workforce routing for the kanban dispatcher.

Governance:
- **Opt-in.** Routing only runs when ``kanban.specialist_routing`` is true
  in config.yaml; otherwise ``route_task`` returns None and the dispatcher
  takes its existing path untouched.
- **Fail-open.** Any failure (config read, roster read, LLM error, unknown
  pick) degrades to the existing ``kanban.default_assignee`` behavior —
  routing is advisory and never changes the dispatcher's outcome.
- **Dispatch never blocks.** The auxiliary LLM call is bounded
  (temperature=0, max_tokens=256, timeout=30) and fully wrapped; a routing
  miss or provider outage falls through to the same default_assignee path
  the dispatcher already uses (#27145).

The roster is matched at dispatch time (creation-time routing lives in
``kanban_decompose``); wiring into the dispatcher tick lands separately.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PICK_SYSTEM_PROMPT = (
    "You route kanban tasks to specialist worker profiles. You are given a "
    "task description and a roster of profiles (name + description). Reply "
    "with EXACTLY ONE profile name from the roster — the single best fit for "
    "the task. Reply with the profile name only: no quotes, no punctuation, "
    "no explanation. If no profile fits the task, reply with the "
    "generalist/fallback profile from the roster (e.g. 'default')."
)


def _roster_entries(roster: Any) -> list[dict]:
    """Extract ``{name, description}`` entries from a roster dict.

    The roster dict shape is ``{"profiles": [{"name": ..., "description":
    ...}, ...]}`` — matching what ``route_task`` accepts directly and what
    ``_load_roster`` builds from the live profile roster.
    """
    profiles: Any = []
    if isinstance(roster, dict):
        profiles = roster.get("profiles") or []
    if not isinstance(profiles, list):
        profiles = []
    entries: list[dict] = []
    for profile in profiles:
        if isinstance(profile, str):
            name = profile.strip()
            if name:
                entries.append({"name": name, "description": ""})
            continue
        if not isinstance(profile, dict):
            continue
        name = (profile.get("name") or "").strip()
        if not name:
            continue
        entries.append({
            "name": name,
            "description": (profile.get("description") or "").strip(),
        })
    return entries


def _format_roster_lines(entries: list[dict]) -> str:
    lines = []
    for entry in entries:
        description = entry.get("description") or ""
        suffix = f" — {description}" if description else ""
        lines.append(f"  - {entry['name']}{suffix}")
    return "\n".join(lines)


def _load_roster() -> dict:
    """Read the live profile roster via the decompose reader.

    ``hermes_cli.kanban_decompose._build_roster`` is the canonical roster
    source: it returns ``(entries, valid_names)`` with each entry shaped
    ``{name, description, has_description}``, sourced from
    ``hermes_cli.profiles.list_profiles()``. Shaped here into the
    ``{"profiles": [...]}`` dict ``route_task`` consumes.
    """
    from hermes_cli import kanban_decompose

    raw_entries, _valid_names = kanban_decompose._build_roster()
    return {
        "profiles": [
            {
                "name": entry.get("name", ""),
                "description": entry.get("description", ""),
            }
            for entry in raw_entries
        ],
    }


def _sanitize_pick(raw: str) -> str:
    """Sanitize a raw LLM reply down to a plausible profile name.

    Takes the first non-empty line, strips wrapping backticks / quotes /
    asterisks and trailing punctuation. Deliberately does NOT split on
    whitespace — profile names may contain spaces.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            text = stripped
            break
    changed = True
    while changed:
        changed = False
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "`\"'*":
            text = text[1:-1].strip()
            changed = True
        while text and text[-1] in ".,;:!":
            text = text[:-1].rstrip()
            changed = True
    return text.strip()


def _llm_raw_pick(task_desc: str, roster_entries: list[dict]) -> str:
    """Raw auxiliary-LLM call: returns the stripped reply text.

    Raises on provider failure — the caller owns the fail-open fallback.
    """
    from agent.auxiliary_client import call_llm

    user_msg = (
        f"Task:\n{task_desc}\n\n"
        f"Roster (reply with exactly one of these names):\n"
        f"{_format_roster_lines(roster_entries)}\n\n"
        "Reply with the single best-fit profile name only."
    )
    resp = call_llm(
        task="kanban_specialist",
        messages=[
            {"role": "system", "content": _PICK_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0,
        max_tokens=256,
        timeout=30,
    )
    raw = resp.choices[0].message.content or ""
    return raw.strip()


def _llm_pick_assignee(task_desc: str, roster_entries: list[dict]) -> str:
    """Ask the auxiliary LLM to pick one roster name for the task.

    Returns a sanitized reply (see :func:`_sanitize_pick`) — LLMs often
    wrap picks in backticks/quotes/asterisks or append punctuation and
    explanations. Raises on provider failure — the caller (``route_task``)
    owns the fail-open fallback.
    """
    return _sanitize_pick(_llm_raw_pick(task_desc, roster_entries))


def route_task(task_desc: str, roster: Any = None) -> Optional[str]:
    """Resolve a specialist assignee for ``task_desc``.

    Returns a roster-valid profile name, or None when routing cannot
    produce one (the caller then uses its existing ``kanban.default_assignee``
    path, which handles None with correct event semantics).

    Semantics (dual-None contract — every fallback that cannot produce a
    spawnable name degrades to None):

    ================  =============================================
    routing disabled  None
    empty roster      None
    config failure    None (outer fail-open)
    LLM error         default_assignee if it is a roster name, else None
    unknown pick      default_assignee if it is a roster name, else None
    valid pick        the picked name
    ================  =============================================

    Task-3 wiring note: routing runs inside the dispatch lock, so a
    per-tick routing breaker (skip routing for the remainder of the tick
    after the first LLM failure) is REQUIRED at wiring time to bound
    N x 30s serial auxiliary calls per tick.
    """
    try:
        from hermes_cli import config as config_mod

        cfg = config_mod.load_config() or {}
        kanban_cfg = cfg.get("kanban") or {}
        if not kanban_cfg.get("specialist_routing"):
            return None
        if roster is None:
            roster = _load_roster()
        entries = _roster_entries(roster)
        if not entries:
            return None
        roster_names = {entry["name"] for entry in entries}
        default = ((kanban_cfg.get("default_assignee") or "") or "").strip() or None
        fallback = default if default in roster_names else None
        try:
            pick = _llm_pick_assignee(task_desc, entries)
        except Exception as exc:
            logger.warning(
                "kanban specialist routing: LLM pick failed (%s); "
                "falling back to default_assignee %r", exc, fallback,
            )
            return fallback
        pick = (pick or "").strip()
        if not pick or pick not in roster_names:
            logger.info(
                "kanban specialist routing: pick %r not in roster; "
                "falling back to default_assignee %r", pick, fallback,
            )
            return fallback
        return pick
    except Exception as exc:
        logger.warning(
            "kanban specialist routing: routing skipped (%s)", exc,
        )
        return None
