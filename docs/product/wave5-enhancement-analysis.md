# Wave 5 Strategic ROI Enhancement Analysis & Roadmap

## Executive Overview

With Waves 1–4 establishing treasury reinvestment, Merkle audit integrity, SLA fulfillment, saga rollbacks, and substrate drift auto-healing, **Wave 5** focuses on **Automated Metered Customer Billing, Supply-Chain Security Gatekeeping, Model Inventory Health Probing, and Institutional Journey Harvester**.

---

## Wave 5 Strategic Investment Matrix

| Priority | Enhancement | Target System / Modules | Economic Impact | Competitive Moat Created | Effort | Priority Score |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **#1** | **Automated Metered Usage Billing & Invoicing Engine** | [metered_billing.py](file:///home/mike/Projects/hermes-agent/hermes_cli/metered_billing.py)<br>[finance_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/finance_db.py) | Automatically meters customer usage, accumulates microminor units, generates reconciled invoices, and queues treasury payment intents. | **Autonomous Revenue Engine.** Zero-touch customer billing & collection. | Medium (2 days) | **290.0** |
| **#2** | **Supply-Chain Security Audit & Dependency Gatekeeper** | [security_audit.py](file:///home/mike/Projects/hermes-agent/hermes_cli/security_audit.py)<br>[objective_policy.py](file:///home/mike/Projects/hermes-agent/hermes_cli/objective_policy.py) | Integrates OSV.dev vulnerability scanning directly into permit evaluation, escalating permits targeting compromised PyPI/npm components. | **Enterprise Security Moat.** Real-time supply-chain vulnerability protection. | Medium (2 days) | **230.0** |
| **#3** | **Curated Model & Provider Inventory Health Prober** | [inventory.py](file:///home/mike/Projects/hermes-agent/hermes_cli/inventory.py)<br>[model_cost_guard.py](file:///home/mike/Projects/hermes-agent/hermes_cli/model_cost_guard.py) | Probes provider API health, latency, and pricing across active inventory, auto-routing execution to optimal model endpoints. | **High Performance.** Lowest latency and cost across multi-provider setups. | Low (1 day) | **180.0** |
| **#4** | **Longitudinal Journey & Achievement Milestone Harvester** | [journey.py](file:///home/mike/Projects/hermes-agent/hermes_cli/journey.py)<br>[hermes_state.py](file:///home/mike/Projects/hermes-agent/hermes_state.py) | Indexes corporate achievements ($10k revenue, 100 objectives, 0 CVEs) into an auditable institutional memory graph. | **Institutional Moat.** Accumulated corporate history & learning timeline. | Low (1 day) | **140.0** |

---

## Detailed Specifications

### 1. Automated Metered Usage Billing & Invoicing Engine
* **Context:** `metered_billing.py` tracks microminor usage events and carries.
* **Intervention:**
  1. Add `run_automated_customer_billing(conn, organization_id, customer_id, through_at)` in [metered_billing.py](file:///home/mike/Projects/hermes-agent/hermes_cli/metered_billing.py).
  2. Aggregates unbilled usage events, computes accumulated minor amounts, records a billing run, and registers a customer invoice in `accounting_db`.

### 2. Supply-Chain Security Audit & Dependency Gatekeeper
* **Context:** `security_audit.py` queries OSV.dev for PyPI/npm vulnerabilities.
* **Intervention:**
  1. Add `assert_supply_chain_security_admissible(conn, organization_id, components)` in [security_audit.py](file:///home/mike/Projects/hermes-agent/hermes_cli/security_audit.py).
  2. Checks component vulnerabilities against policy thresholds and escalates action permits if CRITICAL or HIGH findings exist.

### 3. Curated Model & Provider Inventory Health Prober
* **Context:** `inventory.py` manages provider inventory context.
* **Intervention:**
  1. Add `probe_model_inventory_health(conn, organization_id)` in [inventory.py](file:///home/mike/Projects/hermes-agent/hermes_cli/inventory.py).
  2. Benchmarks provider options and returns an ordered list of optimal active model providers based on availability and cost.

### 4. Longitudinal Journey & Achievement Milestone Harvester
* **Context:** `journey.py` renders learning timelines.
* **Intervention:**
  1. Add `harvest_company_journey_milestones(conn, organization_id)` in [journey.py](file:///home/mike/Projects/hermes-agent/hermes_cli/journey.py).
  2. Scans objectives, treasury entries, and verification records to extract key corporate milestones and output a structured journey graph.

---

## Action Plan

We will proceed with implementing **Wave 5** sequentially:
1. Implement **Automated Metered Customer Billing Engine** (`metered_billing.py`).
2. Implement **Supply-Chain Security Audit Gatekeeper** (`security_audit.py`).
3. Implement **Model Inventory Health Prober** (`inventory.py`).
4. Implement **Journey Achievement Milestone Harvester** (`journey.py`).
5. Verify with master test suite execution across all 23 test modules.
