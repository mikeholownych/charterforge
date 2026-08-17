# Wave 2 Strategic ROI Enhancement Analysis & Action Plan

## Executive Overview

Following the successful implementation of Wave 1 (Closed-Loop Re-Budgeting, Multi-Verification Proof-of-Intent, Automated Tax Harvesting, Skill Gap Capacity Mining, and Self-Healing Circuit Breakers), Charterforge has established an unassailable financial and evidence governance baseline.

This document outlines **Wave 2 Strategic Enhancements** designed to maximize operational throughput, enforce contractual SLAs, automate hypothesis-driven strategy optimization, and minimize model token burn.

---

## Wave 2 Strategic Investment Matrix

| Priority | Enhancement | Target System / Modules | Economic Impact | Competitive Moat Created | Effort | Priority Score |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **#1** | **Automated Commitment & SLA Fulfillment Engine** | [business_commitments.py](file:///home/mike/Projects/hermes-agent/hermes_cli/business_commitments.py)<br>[objective_adapters.py](file:///home/mike/Projects/hermes-agent/hermes_cli/objective_adapters.py) | Prevents SLA penalty fees, missed delivery dates, and client contract disputes. | **High Moat.** Automated evidence-backed contractual commitment tracking. | Medium (2 days) | **240.0** |
| **#2** | **Autonomous Strategy A/B Experiment Evaluator** | [business_metrics.py](file:///home/mike/Projects/hermes-agent/hermes_cli/business_metrics.py)<br>[objective_adapters.py](file:///home/mike/Projects/hermes-agent/hermes_cli/objective_adapters.py) | Automatically routes execution to winning operational strategies, dropping underperforming paths. | **High Moat.** Self-optimizing business strategy loop based on empirical metric observations. | Medium (2 days) | **180.0** |
| **#3** | **Regulatory Compliance Deadline Harvester** | [compliance_deadlines.py](file:///home/mike/Projects/hermes-agent/hermes_cli/compliance_deadlines.py)<br>[regulatory_compliance.py](file:///home/mike/Projects/hermes-agent/hermes_cli/regulatory_compliance.py) | Eliminates statutory filing penalties and multi-jurisdiction compliance gridlock. | **Defensible Moat.** Multi-jurisdiction regulatory deadline & evidence tracking. | Low (1 day) | **120.0** |
| **#4** | **Dynamic Model Token & Cost Velocity Guard** | [resource_budget.py](file:///home/mike/Projects/hermes-agent/hermes_cli/resource_budget.py)<br>[model_cost_guard.py](file:///home/mike/Projects/hermes-agent/hermes_cli/model_cost_guard.py) | Reduces token expenditure by 30-50% by throttling runaways and routing routine tasks to light models. | **Efficiency Lever.** Bounded operational cost per completed objective. | Low (1 day) | **90.0** |

---

## Detailed Specifications

### 1. Automated Commitment & SLA Fulfillment Engine
* **Context:** `business_commitments.py` tracks contractual obligations (deliverables, SLAs, payment terms, grace periods).
* **Intervention:**
  1. Add `auto_fulfill_commitments_from_verifications(conn, organization_id)` in [business_commitments.py](file:///home/mike/Projects/hermes-agent/hermes_cli/business_commitments.py).
  2. Scans pending commitments for `organization_id` and matches required verifiers against passing `verification_records` in `objectives_db`.
  3. When a matching passing verification is found, automatically transitions commitment status to `fulfilled` with `fulfilment_verification_id`.
  4. Raises an urgent escalation trigger when any active commitment is within 24 hours of `due_at` without a passing verification.

### 2. Autonomous Strategy A/B Experiment Evaluator & Route Switcher
* **Context:** `business_metrics.py` manages hypothesis testing (`strategy_experiments`, `strategy_experiment_evaluations`).
* **Intervention:**
  1. Add `evaluate_and_switch_strategy_routes(conn, organization_id)` in [business_metrics.py](file:///home/mike/Projects/hermes-agent/hermes_cli/business_metrics.py).
  2. Analyzes metric observations against success thresholds. When an experiment reaches `supported` verdict, automatically marks the strategy route as authoritative for future planner invocations.
  3. When verdict is `not_supported`, automatically flags the strategy route as deprecated to prevent wasted execution cycles.

### 3. Regulatory Compliance Deadline Harvester
* **Context:** `compliance_deadlines.py` and `regulatory_compliance.py` track statutory regimes and deadlines.
* **Intervention:**
  1. Add `harvest_jurisdiction_compliance_deadlines(conn, organization_id, jurisdiction, year)` in [compliance_deadlines.py](file:///home/mike/Projects/hermes-agent/hermes_cli/compliance_deadlines.py).
  2. Automatically computes quarterly and annual statutory filing deadlines (e.g. Q1-Q4 tax filings, annual corporate renewals) for active organization jurisdictions.

### 4. Dynamic Model Token & Cost Velocity Guard
* **Context:** `resource_budget.py` manages token budgets and execution limits.
* **Intervention:**
  1. Add `check_cost_velocity_and_recommend_tier(conn, objective_id, token_consumption_window)` in [resource_budget.py](file:///home/mike/Projects/hermes-agent/hermes_cli/resource_budget.py).
  2. If token consumption rate exceeds expected baseline cost velocity, signals the runtime to route sub-tasks to faster/lighter model tiers.

---

## Action Plan

We will proceed with implementing **Wave 2** sequentially:
1. Implement **Automated Commitment & SLA Fulfillment Engine** (`business_commitments.py`).
2. Implement **Autonomous Strategy A/B Experiment Evaluator** (`business_metrics.py`).
3. Implement **Regulatory Compliance Deadline Harvester** (`compliance_deadlines.py`).
4. Implement **Dynamic Model Token & Cost Velocity Guard** (`resource_budget.py`).
5. Run full test suite verification across all modules.
