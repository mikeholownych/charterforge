"""Unit tests for Wave 21 Strategic Enhancements: Joint Venture Profit Sharing Engine, Regulatory Change Harvester, Fraud/AML Detector, and Shareholder Proxy Voting Engine."""

from __future__ import annotations

import sqlite3

from hermes_cli import (
    compliance_deadlines,
    objectives_db,
    organization_db,
    security_audit,
)


def _setup_test_db(tmp_path) -> tuple[sqlite3.Connection, str, str]:
    conn = objectives_db.connect(tmp_path / "authority.db")
    organization_db.ensure_schema(conn)

    parent_id = organization_db.create_organization(
        conn,
        name="ParentCorpW21",
        purpose="Parent Wave 21 testing",
        operator_role="advisor",
        headcount_limit=10,
        payroll_budget_minor=100000,
    )
    sub_id = organization_db.create_organization(
        conn,
        name="JVEntityW21",
        purpose="JV Wave 21 testing",
        operator_role="advisor",
        headcount_limit=5,
        payroll_budget_minor=50000,
    )

    return conn, parent_id, sub_id


def test_execute_joint_venture_profit_split(tmp_path):
    conn, parent_id, sub_id = _setup_test_db(tmp_path)

    jv = organization_db.execute_joint_venture_profit_split(
        conn,
        organization_id=parent_id,
        jv_entity_id=sub_id,
        partner_org_id="partner_corp_alpha",
        net_profit_minor=500000,
        equity_split_pct=40.0,
    )

    assert jv["jv_split_id"].startswith("jvsplit_")
    assert jv["organization_id"] == parent_id
    assert jv["partner_share_minor"] == 200000
    assert jv["parent_share_minor"] == 300000
    assert jv["status"] == "jv_profit_settled"


def test_harvest_regulatory_standard_updates(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    reg = compliance_deadlines.harvest_regulatory_standard_updates(
        conn, organization_id=parent_id, jurisdiction="EU"
    )

    assert reg["regulatory_harvest_id"].startswith("regharvest_")
    assert reg["organization_id"] == parent_id
    assert reg["jurisdiction"] == "EU"
    assert reg["updates_harvested_count"] >= 1
    assert reg["status"] == "regulatory_updates_ingested"


def test_audit_internal_aml_fraud_patterns(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    fraud = security_audit.audit_internal_aml_fraud_patterns(
        conn, organization_id=parent_id
    )

    assert fraud["fraud_audit_id"].startswith("fraud_")
    assert fraud["organization_id"] == parent_id
    assert fraud["aml_risk_score"] == 0.0
    assert fraud["status"] == "clean_audit_passed"


def test_cast_corporate_shareholder_proxy_vote(tmp_path):
    conn, parent_id, _ = _setup_test_db(tmp_path)

    vote = organization_db.cast_corporate_shareholder_proxy_vote(
        conn,
        organization_id=parent_id,
        resolution_id="res_board_101",
        shareholder_id="sh_blackrock",
        vote_choice="yea",
        shares_count=50000,
    )

    assert vote["proxy_vote_id"].startswith("proxy_")
    assert vote["organization_id"] == parent_id
    assert vote["resolution_id"] == "res_board_101"
    assert vote["shares_voted"] == 50000
    assert vote["status"] == "proxy_vote_recorded"
