# Wave 17 Strategic ROI Enhancement Analysis & Roadmap

## Executive Overview

Having established executive audio briefings, data sovereignty routing, IP patent harvesting, and vendor dispute chargebacks (Wave 16), **Wave 17: Autonomous Skill Retraining, Inter-Company IP Royalties & Cross-Border Tax Routing Autopilot** arms Charterforge with **employee skill retraining dispatching, inter-company IP royalty settlement, predictive customer health indexing, and cross-border treasury withholding tax routing optimization**.

---

## Wave 17 Strategic Investment Matrix

| Priority | Enhancement | Target System / Modules | Economic Impact | Competitive Moat Created | Effort | Priority Score |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **#1** | **Autonomous Employee Skill Retraining & Upgrade Dispatcher** | [hiring_policy.py](file:///home/mike/Projects/hermes-agent/hermes_cli/hiring_policy.py)<br>[objectives_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/objectives_db.py) | Provisions dedicated skill retraining objectives for existing agent workers to acquire new capability envelopes without external hiring. | **Autonomous Upskilling Moat.** Continuous zero-cost workforce adaptation. | Medium (2 days) | **620.0** |
| **#2** | **Inter-Company IP Licensing Royalty & Transfer Pricing Engine** | [accounting_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/accounting_db.py)<br>[journey.py](file:///home/mike/Projects/hermes-agent/hermes_cli/journey.py) | Computes inter-company IP licensing royalty fees on subsidiary net revenue and posts automated double-entry transfer pricing settlements. | **Compliant IP Monetization.** Automated inter-company transfer pricing. | Medium (2 days) | **570.0** |
| **#3** | **Predictive Customer Health & NPS Velocity Indexer** | [journey.py](file:///home/mike/Projects/hermes-agent/hermes_cli/journey.py)<br>[business_metrics.py](file:///home/mike/Projects/hermes-agent/hermes_cli/business_metrics.py) | Aggregates support SLA performance, metered consumption trends, and billing stability into a predictive customer health velocity index. | **Proactive Expansion Moat.** Early warning indicators for enterprise accounts. | Low (1 day) | **520.0** |
| **#4** | **Cross-Border Treasury Withholding Tax Optimization Engine** | [finance_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/finance_db.py)<br>[accounting_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/accounting_db.py) | Evaluates bilateral tax treaty rates to select optimal inter-subsidiary transfer paths, minimizing cross-border withholding tax friction. | **Tax Treaty Optimization.** Multi-national treasury tax efficiency. | Low (1 day) | **470.0** |

---

## Detailed Specifications

### 1. Autonomous Employee Skill Retraining & Upgrade Dispatcher
* **Context:** Skill gaps can be resolved by upgrading existing agent worker capability envelopes instead of hiring.
* **Intervention:**
  1. Add `dispatch_employee_skill_retraining_program(conn, organization_id, employee_id, target_capability)` in [hiring_policy.py](file:///home/mike/Projects/hermes-agent/hermes_cli/hiring_policy.py).
  2. Provisions a skill retraining objective and expands employee capability envelopes upon completion.

### 2. Inter-Company IP Licensing Royalty & Transfer Pricing Engine
* **Context:** Subsidiaries leveraging parent company IP bundles must pay governed inter-company licensing royalties.
* **Intervention:**
  1. Add `calculate_and_settle_intercompany_ip_royalties(conn, parent_org_id, child_org_id, net_revenue_minor, royalty_pct=5.0)` in [accounting_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/accounting_db.py).
  2. Calculates royalty payments and records inter-subsidiary transfer clearing entries.

### 3. Predictive Customer Health & NPS Velocity Indexer
* **Context:** Enterprise customer retention requires predictive health indexing based on multi-channel signals.
* **Intervention:**
  1. Add `predict_customer_health_and_nps_velocity(conn, organization_id, customer_id)` in [journey.py](file:///home/mike/Projects/hermes-agent/hermes_cli/journey.py).
  2. Computes composite customer health scores (0-100) and predicts retention probability.

### 4. Cross-Border Treasury Withholding Tax Optimization Engine
* **Context:** Inter-subsidiary treasury transfers cross tax boundaries requiring optimal route selection.
* **Intervention:**
  1. Add `optimize_cross_border_treasury_tax_routing(conn, organization_id, source_org_id, destination_org_id, amount_minor)` in [finance_db.py](file:///home/mike/Projects/hermes-agent/hermes_cli/finance_db.py).
  2. Calculates applicable tax treaty rates and returns optimal inter-subsidiary transfer routes.

---

## Action Plan

We will proceed with implementing **Wave 17** sequentially:
1. Implement **Employee Skill Retraining Dispatcher** (`hiring_policy.py`).
2. Implement **Inter-Company IP Royalty Engine** (`accounting_db.py`).
3. Implement **Predictive Customer Health Indexer** (`journey.py`).
4. Implement **Cross-Border Treasury Tax Optimization Engine** (`finance_db.py`).
5. Verify with master test suite execution across all test modules.
