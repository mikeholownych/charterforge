# Autonomous Business OS

## Approved Boundary

Charterforge operates business objectives unattended within configured authority,
budgets, data-handling rules, and operator stop controls. Routine execution and
recovery must not depend on a human replying or issuing a resume command.
Missing authority, credentials, or funds cannot be invented or bypassed.

Blocked work is durably deferred, replanned, or abandoned according to policy;
it is never reported as successful. Other eligible objectives continue.
Completion requires independent verification of the intended business outcome.

## Architecture

Extend the existing ObjectiveRuntime and objective_service execution path.
Reuse policy evaluation, exact-action permits, independent verification,
resource leases, generation fencing, durable events, and operational controls.
GoalManager remains a conversational entry surface, not a second authority store.
No new core tools or mid-conversation prompt/toolset reconstruction are required.

## Delivery Order

1. Recover the baseline: working imports, useful Git probes, isolated credentials,
   preserved governance wiring, and reproducible tests from tracked files.
2. Autonomous objective lifecycle: durable retries, bounded replanning, restart
   recovery, explicit blocked outcomes, and independently verified completion.
3. Provider recovery among configured authorized providers within budget and
   data-handling constraints.
4. Skill evolution with isolated evaluation, controlled promotion, and rollback.
5. Specialist workforce using durable tasks, exclusive claims, and bounded grants.
6. Deployment automation with preflight, canary verification, and rollback.
7. Architecture checks and isolated, tested refactoring proposals.
8. Incident response using preauthorized recovery actions and recovery verification.

Each stage needs its own implementation plan and acceptance evidence before the
next stage is enabled. Baseline recovery is a prerequisite, not evidence that
the autonomy enhancements have shipped.

## Acceptance Gates

Exercise real imports and temporary profile state through the repository test
runner. Prove restart recovery, competing claims, idempotent effects, budget
exhaustion, stale/revoked permits, and stop controls between authorization and
execution. Verify that blocked objectives do not prevent unrelated eligible work.
Never infer runtime health from syntax checks or unrelated passing test suites.

## Current First Slice

The baseline plan is at
`docs/superpowers/plans/2026-09-06-autonomy-baseline-recovery.md`.
It repairs the confirmed full-argv contract of bounded_git_probe first; state
imports, credential hydration, and objective-watcher restoration remain separate
baseline gates. Existing untracked source files must be preserved.
