# Wave 4 Strategic ROI Enhancement Analysis & Roadmap

## Executive Overview

Having established a self-funding treasury engine (Wave 1), automated SLA fulfillment (Wave 2), and Merkle audit integrity (Wave 3), Charterforge is now positioning for **Wave 4: Autonomous Procurement, Saga Compensation Rollbacks, Substrate Drift Auto-Healing, and Verifiable Communication Receipts**.

---

## Wave 4 Strategic Investment Matrix

| Priority | Enhancement | Target System / Modules | Economic Impact | Competitive Moat Created | Effort | Priority Score |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **#1** | **Automated Procurement Policy Evaluator & Vendor Selector** | [procurement_policy.py](file:///home/mike/Projects/hermes-agent/hermes_cli/procurement_policy.py)<br>[finance_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/finance_db.py) | Eliminates manual vendor research overhead and enforces capital spend ceilings for build vs. buy decisions. | **Defensible Moat.** Governed capital procurement policy engine. | Medium (2 days) | **260.0** |
| **#2** | **Autonomous Saga Rollback & Compensation Dispatcher** | [compensation.py](file:///home/mike/Projects/hermes-agent/hermes_cli/compensation.py)<br>[objective_adapters.py](file:///home/mike/Projects/hermes-agent/hermes_cli/objective_adapters.py) | Automatically rolls back unverified multi-step side-effects (cloud resources, payment holds, DNS updates), eliminating financial leak. | **Unrivaled Execution Reliability.** Self-cleaning saga transactions. | Medium (2 days) | **220.0** |
| **#3** | **Substrate Schema & Charter Runtime Drift Auto-Healer** | [runtime_drift.py](file:///home/mike/Projects/hermes-agent/hermes_cli/runtime_drift.py)<br>[operational_control.py](file:///home/mike/Projects/hermes-agent/hermes_cli/operational_control.py) | Prevents substrate crash failures due to schema updates or charter drift during unattended runs. | **Zero-Downtime Moat.** Continuous substrate fingerprinting and auto-healing. | Low (1 day) | **170.0** |
| **#4** | **Governed Communication Dispatcher & Proof Receipts** | [company_email.py](file:///home/mike/Projects/hermes-agent/hermes_cli/company_email.py)<br>[verification_evidence.py](file:///home/mike/Projects/hermes-agent/hermes_cli/verification_evidence.py) | Attaches verifiable cryptographic evidence envelopes to outbound client, vendor, and regulatory communications. | **Auditable Governance.** Verifiable proof of transmission for corporate actions. | Low (1 day) | **130.0** |

---

## Detailed Specifications

### 1. Automated Procurement Policy Evaluator & Vendor Selector
* **Context:** `procurement_policy.py` governs build/FOSS/buy decisions.
* **Intervention:**
  1. Add `auto_evaluate_procurement_case(conn, organization_id, objective_id, service_name, estimated_cost_minor)` in [procurement_policy.py](file:///home/mike/Projects/hermes-agent/hermes_cli/procurement_policy.py).
  2. Evaluates available treasury surplus and capital ceilings to select `choice`: `existing`, `foss`, `build`, `buy`, or `defer`.

### 2. Autonomous Saga Rollback & Compensation Dispatcher
* **Context:** `compensation.py` tracks saga compensation obligations.
* **Intervention:**
  1. Add `dispatch_saga_compensations(conn, organization_id)` in [compensation.py](file:///home/mike/Projects/hermes-agent/hermes_cli/compensation.py).
  2. Scans open compensation obligations for failed actions and dispatches reverse compensation permits to clean up external resources.

### 3. Substrate Schema & Charter Runtime Drift Auto-Healer
* **Context:** `runtime_drift.py` tracks baseline fingerprints.
* **Intervention:**
  1. Add `probe_and_auto_rebaseline_runtime_drift(conn, organization_id, actor)` in [runtime_drift.py](file:///home/mike/Projects/hermes-agent/hermes_cli/runtime_drift.py).
  2. Computes schema fingerprints and auto-updates baselines for backward-compatible additions while pausing autonomy for breaking changes.

### 4. Governed Communication Dispatcher & Proof Receipts
* **Context:** `company_email.py` handles communication.
* **Intervention:**
  1. Add `dispatch_governed_email_with_proof(conn, organization_id, objective_id, recipient, subject, body)` in [company_email.py](file:///home/mike/Projects/hermes-agent/hermes_cli/company_email.py).
  2. Transmits communication and records proof-of-dispatch evidence envelope in `verification_records`.

---

## Action Plan

We will proceed with implementing **Wave 4** sequentially:
1. Implement **Automated Procurement Policy Evaluator** (`procurement_policy.py`).
2. Implement **Autonomous Saga Rollback Dispatcher** (`compensation.py`).
3. Implement **Substrate Schema Drift Auto-Healer** (`runtime_drift.py`).
4. Implement **Governed Communication Dispatcher** (`company_email.py`).
5. Verify with master test suite execution.
