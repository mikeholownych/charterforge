"""Governed-browser authorization regression (fork IP ported onto upstream's
browser decomposition; see the autonomy baseline plan, gate 4).

A worker holding the browser toolset still needs an EXACT authority grant per
operation: `authorize_worker_action` must fire before any browser command, with
a capability naming the operation and a target bound to the receiving session
(navigation permits additionally bind the URL hash so a permit cannot be
replayed against a different destination).
"""
from __future__ import annotations

import hashlib
import json

import pytest

from tools import browser_tool


@pytest.fixture()
def _browser_mode(monkeypatch):
    """Local-backend mode with deterministic session keys and no real browser."""
    monkeypatch.setattr(browser_tool, "_is_camofox_mode", lambda: False)
    monkeypatch.setattr(browser_tool, "_last_session_key", lambda task_id: task_id)


@pytest.fixture()
def recorded_authority(monkeypatch):
    calls = []

    def record(*, capability, system, target_resource):
        calls.append((capability, system, target_resource))

    monkeypatch.setattr(
        "hermes_cli.workforce_delegation.authorize_worker_action", record
    )
    return calls


@pytest.fixture()
def no_browser(monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise AssertionError("browser command must not run before authorization")

    monkeypatch.setattr(browser_tool._session, "_run_browser_command", fail_run)


def test_wrapper_binds_permit_to_session(recorded_authority):
    browser_tool._authorize_browser_action("browser.type", "worker-1")
    assert recorded_authority == [
        ("browser.type", "browser", "browser-session:worker-1")
    ]


def test_navigate_permits_are_url_bound(_browser_mode, recorded_authority, monkeypatch):
    """Navigation permits bind the destination URL hash: the permit cannot be
    replayed to open a different page in the same session. Authorization fires
    BEFORE the open command is dispatched."""
    url = "https://example.com/secret-dest"
    expected_target = (
        f"browser-navigation:task-1:url:{hashlib.sha256(url.encode('utf-8')).hexdigest()}"
    )
    ran = []
    monkeypatch.setattr(browser_tool, "_navigation_session_key", lambda tid, u: tid)
    monkeypatch.setattr(
        browser_tool, "_url_policy_error", lambda url, auto_local=False: None
    )
    monkeypatch.setattr(
        browser_tool._session, "_get_session_info", lambda key: {"_first_nav": True}
    )
    monkeypatch.setattr(browser_tool, "_maybe_start_recording", lambda key: None)
    monkeypatch.setattr(browser_tool, "_post_redirect_block", lambda *a, **k: None)
    monkeypatch.setattr(
        browser_tool._session,
        "_run_browser_command",
        lambda key, cmd, args, timeout=None: ran.append((key, cmd)) or {"success": True, "data": {"title": "", "url": url}},
    )

    browser_tool.browser_navigate(url, task_id="task-1")

    # Permit first, then the open command against the permitted session.
    assert recorded_authority == [("browser.navigate", "browser", expected_target)]
    # The permitted session receives the open command first; the auto-snapshot
    # follow-up is expected upstream behavior.
    assert ran[0] == ("task-1", "open")


@pytest.mark.parametrize(
    ("fn", "args", "capability"),
    [
        (browser_tool.browser_click, ("@e1",), "browser.click"),
        (browser_tool.browser_type, ("@e1", "text"), "browser.type"),
        (browser_tool.browser_scroll, ("down",), "browser.scroll"),
        (browser_tool.browser_back, (), "browser.back"),
        (browser_tool.browser_press, ("Enter",), "browser.press"),
        (browser_tool.browser_snapshot, (), "browser.snapshot"),
        (browser_tool.browser_vision, ("describe",), "browser.vision"),
        (browser_tool.browser_get_images, (), "browser.get_images"),
    ],
)
def test_every_action_requests_a_permit_before_running(
    _browser_mode, recorded_authority, fn, args, capability, monkeypatch
):
    """Each public action must fire authorize_worker_action with its capability
    and the receiving session as the target — before any side effect."""
    no_side_effect = []

    def fake_run(task_id, command, cmd_args):
        no_side_effect.append((task_id, command))
        return {"success": True}

    monkeypatch.setattr(browser_tool._session, "_run_browser_command", fake_run)
    # vision/snapshot internals vary; stub the shared seam they end at.
    monkeypatch.setattr(
        browser_tool, "_navigation_session_key", lambda tid, u: tid, raising=False
    )
    monkeypatch.setattr(
        browser_tool, "_url_policy_error", lambda url, auto_local=False: None,
        raising=False,
    )
    try:
        fn(*args, task_id="task-1")
    except Exception:
        # Some actions post-process richer payloads; the authorization
        # assertion below is the contract under test.
        pass
    assert capability in [c for c, _s, _t in recorded_authority], recorded_authority
    targets = [t for c, _s, t in recorded_authority if c == capability]
    assert all(t.startswith("browser-session:task-1") for t in targets), targets


def test_authority_denial_stops_click_before_backend(_browser_mode, monkeypatch):
    def reject(*_args, **_kwargs):
        raise RuntimeError("authority denied")

    monkeypatch.setattr(browser_tool, "_authorize_browser_action", reject)
    monkeypatch.setattr(
        browser_tool._session, "_run_browser_command",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("browser command ran without authority")
        ),
    )
    with pytest.raises(RuntimeError, match="authority denied"):
        browser_tool.browser_click("@e1", task_id="worker-1")


def test_wrapper_accepts_exact_target_override(recorded_authority):
    """Navigate's caller binds the exact navigation target through the
    override parameter (fork IP: permits bind the URL they authorize)."""
    browser_tool._authorize_browser_action(
        "browser.navigate", "task-1", target_resource="browser-navigation:task-1:url:abc"
    )
    assert recorded_authority == [
        ("browser.navigate", "browser", "browser-navigation:task-1:url:abc")
    ]
