"""Unit tests for multi-verification proof-of-intent engine (external read-back verifiers)."""

from __future__ import annotations

import time

from hermes_cli.objective_adapters import (
    ActionExecutorRegistry,
    ActionProposal,
    ExecutionOutcome,
    IndependentVerifierRegistry,
    register_external_verifiers,
)


def _setup_registries():
    executor = ActionExecutorRegistry(identity="test_executor")
    verifier = IndependentVerifierRegistry(identity="control:verification")
    register_external_verifiers(executor, verifier)
    return executor, verifier


def test_github_pr_merged_verifier_pass():
    _, verifier = _setup_registries()

    action = ActionProposal(
        action_type="github.pr.merge",
        payload={
            "system": "github",
            "target_resource": "owner/repo",
            "repo": "owner/repo",
            "pr_number": 42,
            "idempotency_key": "1234567890123456",
        },
        expected_outcome="PR merged",
        required_capability="github.write",
        verification_method="github.pr.merged",
        risk_class="low",
        reversible=False,
        rationale="Merge release PR",
        estimated_cost_minor=0,
    )

    execution = ExecutionOutcome(
        status="succeeded",
        result={
            "status": "merged",
            "merged": True,
            "commit_sha": "def456",
            "merged_at": int(time.time()),
            "pr_number": 42,
        },
    )

    outcome = verifier.verify(action, execution)

    assert outcome.verdict == "pass"
    assert outcome.evidence["source_kind"] == "provider_readback"
    assert outcome.evidence["source_reference"] == "github:owner/repo:pr:42"
    assert outcome.evidence["facts"]["status"] == "merged"
    assert outcome.evidence["facts"]["merged"] is True
    assert outcome.evidence["facts"]["commit_sha"] == "def456"


def test_github_pr_merged_verifier_fail():
    _, verifier = _setup_registries()

    action = ActionProposal(
        action_type="github.pr.merge",
        payload={
            "system": "github",
            "target_resource": "owner/repo",
            "repo": "owner/repo",
            "pr_number": 43,
            "idempotency_key": "1234567890123457",
        },
        expected_outcome="PR merged",
        required_capability="github.write",
        verification_method="github.pr.merged",
        risk_class="low",
        reversible=False,
        rationale="Merge release PR",
        estimated_cost_minor=0,
    )

    execution = ExecutionOutcome(
        status="succeeded",
        result={
            "status": "open",
            "merged": False,
            "reason": "CI checks pending",
            "pr_number": 43,
        },
    )

    outcome = verifier.verify(action, execution)

    assert outcome.verdict == "fail"
    assert outcome.evidence["facts"]["merged"] is False
    assert outcome.evidence["facts"]["reason"] == "CI checks pending"


def test_http_response_200_verifier_pass():
    _, verifier = _setup_registries()

    action = ActionProposal(
        action_type="http.get",
        payload={
            "system": "http",
            "target_resource": "https://api.example.com/health",
            "url": "https://api.example.com/health",
            "idempotency_key": "1234567890123458",
        },
        expected_outcome="200 OK",
        required_capability="http.read",
        verification_method="http.response.200",
        risk_class="low",
        reversible=True,
        rationale="Health check",
        estimated_cost_minor=0,
    )

    execution = ExecutionOutcome(
        status="succeeded",
        result={
            "status_code": 200,
            "headers": {"content-type": "application/json"},
            "body_sha256": "abc123hash",
        },
    )

    outcome = verifier.verify(action, execution)

    assert outcome.verdict == "pass"
    assert outcome.evidence["source_reference"] == "http:https://api.example.com/health"
    assert outcome.evidence["facts"]["status_code"] == 200
    assert outcome.evidence["facts"]["body_sha256"] == "abc123hash"


def test_http_response_200_verifier_fail():
    _, verifier = _setup_registries()

    action = ActionProposal(
        action_type="http.get",
        payload={
            "system": "http",
            "target_resource": "https://api.example.com/health",
            "url": "https://api.example.com/health",
            "idempotency_key": "1234567890123459",
        },
        expected_outcome="200 OK",
        required_capability="http.read",
        verification_method="http.response.200",
        risk_class="low",
        reversible=True,
        rationale="Health check",
        estimated_cost_minor=0,
    )

    execution = ExecutionOutcome(
        status="succeeded",
        result={
            "status_code": 503,
            "headers": {"content-type": "text/html"},
            "body_sha256": "errorhash",
        },
    )

    outcome = verifier.verify(action, execution)

    assert outcome.verdict == "fail"
    assert outcome.evidence["facts"]["status_code"] == 503
