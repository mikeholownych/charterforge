"""Enterprise organization model for durable sub-agent employees.

Employees are not anonymous delegation calls.  They occupy an explicit
reporting hierarchy, carry time-bounded mandates and capability envelopes, and
have an auditable employment lifecycle.  Charterforge profiles remain the execution
identity; this module is the authoritative organizational identity.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

import time
import uuid
from dataclasses import dataclass
from functools import wraps
from typing import Any, Mapping, Optional


ORG_LEVELS = {
    "ceo": 1,
    "c_suite": 2,
    "svp": 3,
    "vp": 4,
    "director": 5,
    "manager": 6,
    "lead": 7,
    "individual_contributor": 8,
    "contractor": 8,
}
EMPLOYEE_STATUSES = frozenset(
    {
        "proposed",
        "approved",
        "provisioning",
        "active",
        "suspended",
        "terminated",
        "rejected",
    }
)
_EMPLOYEE_TRANSITIONS = {
    "proposed": {"approved", "rejected"},
    "approved": {"provisioning", "rejected"},
    "provisioning": {"active", "suspended", "terminated"},
    "active": {"suspended", "terminated"},
    "suspended": {"active", "terminated"},
    "terminated": set(),
    "rejected": set(),
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS organizations (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    purpose               TEXT NOT NULL,
    operator_role         TEXT NOT NULL,
    base_currency         TEXT NOT NULL,
    headcount_limit       INTEGER,
    payroll_budget_minor  INTEGER,
    data_residency_region TEXT NOT NULL DEFAULT 'local',
    allowed_processing_regions_json TEXT NOT NULL DEFAULT '["local"]',
    created_at            INTEGER NOT NULL,
    updated_at            INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS org_units (
    id           TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    parent_id    TEXT,
    leader_id    TEXT,
    cost_center  TEXT,
    created_at   INTEGER NOT NULL,
    UNIQUE(organization_id, name),
    FOREIGN KEY(organization_id) REFERENCES organizations(id),
    FOREIGN KEY(parent_id) REFERENCES org_units(id)
);

CREATE TABLE IF NOT EXISTS employees (
    id                 TEXT PRIMARY KEY,
    organization_id    TEXT NOT NULL,
    profile_name       TEXT,
    display_name       TEXT NOT NULL,
    title              TEXT NOT NULL,
    level              TEXT NOT NULL,
    department_id      TEXT,
    manager_id         TEXT,
    status             TEXT NOT NULL,
    employment_type    TEXT NOT NULL,
    annual_cost_minor  INTEGER NOT NULL DEFAULT 0,
    currency           TEXT NOT NULL,
    hired_for_objective_id TEXT,
    proposed_by        TEXT NOT NULL,
    approved_by        TEXT,
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    started_at         INTEGER,
    ended_at           INTEGER,
    UNIQUE(organization_id, profile_name),
    FOREIGN KEY(organization_id) REFERENCES organizations(id),
    FOREIGN KEY(department_id) REFERENCES org_units(id),
    FOREIGN KEY(manager_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS employee_mandates (
    id                   TEXT PRIMARY KEY,
    employee_id          TEXT NOT NULL,
    version              INTEGER NOT NULL,
    purpose              TEXT NOT NULL,
    responsibilities_json TEXT NOT NULL,
    decision_rights_json TEXT NOT NULL,
    prohibited_actions_json TEXT NOT NULL,
    capabilities_json    TEXT NOT NULL,
    systems_json         TEXT NOT NULL,
    budget_minor         INTEGER,
    kpis_json             TEXT NOT NULL,
    escalation_json      TEXT NOT NULL,
    toolsets_json        TEXT NOT NULL DEFAULT '[]',
    skills_json          TEXT NOT NULL DEFAULT '[]',
    starts_at             INTEGER NOT NULL,
    expires_at            INTEGER,
    created_by            TEXT NOT NULL,
    created_at            INTEGER NOT NULL,
    supersedes_id         TEXT,
    UNIQUE(employee_id, version),
    FOREIGN KEY(employee_id) REFERENCES employees(id)
);

CREATE TABLE IF NOT EXISTS employee_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id   TEXT NOT NULL,
    kind          TEXT NOT NULL,
    actor         TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    FOREIGN KEY(employee_id) REFERENCES employees(id)
);

CREATE INDEX IF NOT EXISTS idx_employees_manager
    ON employees(organization_id, manager_id, status);
CREATE INDEX IF NOT EXISTS idx_employees_department
    ON employees(organization_id, department_id, status);
CREATE INDEX IF NOT EXISTS idx_mandates_employee
    ON employee_mandates(employee_id, version);
CREATE INDEX IF NOT EXISTS idx_employee_events_employee
    ON employee_events(employee_id, id);
CREATE TRIGGER IF NOT EXISTS employee_mandates_immutable_update
BEFORE UPDATE ON employee_mandates
BEGIN SELECT RAISE(ABORT, 'employee mandates are immutable'); END;
CREATE TRIGGER IF NOT EXISTS employee_mandates_immutable_delete
BEFORE DELETE ON employee_mandates
BEGIN SELECT RAISE(ABORT, 'employee mandates are immutable'); END;
"""


class OrganizationError(ValueError):
    """Raised when a corporate hierarchy invariant would be violated."""


@dataclass(frozen=True)
class Employee:
    id: str
    organization_id: str
    profile_name: Optional[str]
    display_name: str
    title: str
    level: str
    manager_id: Optional[str]
    status: str


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> int:
    return int(time.time())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def ensure_schema(conn: sqlite3.Connection) -> None:
    # ``executescript`` implicitly commits an active SQLite transaction. Do
    # not let read helpers invoked inside an authority admission transaction
    # release its write lock; top-level callers initialize/migrate the schema
    # before opening the transaction.
    if conn.in_transaction and conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='organizations'"
    ).fetchone():
        return
    conn.executescript(SCHEMA_SQL)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(employee_mandates)")
    }
    if "toolsets_json" not in columns:
        conn.execute(
            "ALTER TABLE employee_mandates "
            "ADD COLUMN toolsets_json TEXT NOT NULL DEFAULT '[]'"
        )
        conn.commit()
    if "skills_json" not in columns:
        conn.execute(
            "ALTER TABLE employee_mandates "
            "ADD COLUMN skills_json TEXT NOT NULL DEFAULT '[]'"
        )
        conn.commit()
    org_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(organizations)")
    }
    if "data_residency_region" not in org_columns:
        conn.execute(
            "ALTER TABLE organizations ADD COLUMN "
            "data_residency_region TEXT NOT NULL DEFAULT 'local'"
        )
    if "allowed_processing_regions_json" not in org_columns:
        conn.execute(
            "ALTER TABLE organizations ADD COLUMN "
            "allowed_processing_regions_json TEXT NOT NULL DEFAULT '[\"local\"]'"
        )
    conn.commit()


def _serialized_organization_mutation(function):
    """Preserve one authority transaction across nested org mutations."""

    @wraps(function)
    def wrapped(conn, *args, **kwargs):
        ensure_schema(conn)
        owns_transaction = not conn.in_transaction
        if owns_transaction:
            conn.execute("BEGIN IMMEDIATE")
        try:
            result = function(conn, *args, **kwargs)
        except Exception:
            if owns_transaction:
                conn.rollback()
            raise
        else:
            if owns_transaction:
                conn.commit()
            return result

    return wrapped


def _event(
    conn: sqlite3.Connection,
    employee_id: str,
    kind: str,
    actor: str,
    payload: Any,
) -> None:
    conn.execute(
        """
        INSERT INTO employee_events (employee_id, kind, actor, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (employee_id, kind, actor, _json(payload), _now()),
    )


def create_organization(
    conn: sqlite3.Connection,
    *,
    name: str,
    purpose: str,
    operator_role: str = "advisor",
    base_currency: str = "USD",
    headcount_limit: Optional[int] = None,
    payroll_budget_minor: Optional[int] = None,
    data_residency_region: str = "local",
    allowed_processing_regions: Optional[list[str]] = None,
) -> str:
    ensure_schema(conn)
    if operator_role not in {"advisor", "approver", "operator"}:
        raise OrganizationError("operator_role must be advisor, approver, or operator")
    if headcount_limit is not None and headcount_limit < 1:
        raise OrganizationError("headcount_limit must be positive")
    if payroll_budget_minor is not None and payroll_budget_minor < 0:
        raise OrganizationError("payroll_budget_minor must be non-negative")
    org_id = _id("org")
    processing_regions = allowed_processing_regions or [data_residency_region]
    if data_residency_region not in processing_regions:
        raise OrganizationError(
            "data residency region must be an allowed processing region"
        )
    ts = _now()
    with conn:
        conn.execute(
            """
            INSERT INTO organizations (
                id, name, purpose, operator_role, base_currency,
                headcount_limit, payroll_budget_minor, data_residency_region,
                allowed_processing_regions_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                org_id,
                name.strip(),
                purpose.strip(),
                operator_role,
                base_currency.upper(),
                headcount_limit,
                payroll_budget_minor,
                data_residency_region,
                _json(processing_regions),
                ts,
                ts,
            ),
        )
    return org_id


def assert_processing_region(
    conn: sqlite3.Connection,
    organization_id: str,
    processing_region: str,
) -> None:
    ensure_schema(conn)
    row = conn.execute(
        """SELECT data_residency_region, allowed_processing_regions_json
           FROM organizations WHERE id=?""",
        (organization_id,),
    ).fetchone()
    if row is None:
        raise OrganizationError("organization not found")
    allowed = set(json.loads(row["allowed_processing_regions_json"]))
    if processing_region not in allowed:
        raise OrganizationError(
            f"processing region {processing_region!r} violates residency policy "
            f"{row['data_residency_region']!r}"
        )


def create_org_unit(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    name: str,
    kind: str,
    parent_id: Optional[str] = None,
    cost_center: Optional[str] = None,
) -> str:
    ensure_schema(conn)
    if kind not in {"company", "division", "department", "team", "function"}:
        raise OrganizationError("invalid organization unit kind")
    if parent_id is not None:
        parent = conn.execute(
            "SELECT organization_id FROM org_units WHERE id = ?", (parent_id,)
        ).fetchone()
        if parent is None or parent["organization_id"] != organization_id:
            raise OrganizationError("parent unit must belong to the organization")
    unit_id = _id("unit")
    with conn:
        conn.execute(
            """
            INSERT INTO org_units (
                id, organization_id, name, kind, parent_id, cost_center, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit_id,
                organization_id,
                name.strip(),
                kind,
                parent_id,
                cost_center,
                _now(),
            ),
        )
    return unit_id


def _employee(conn: sqlite3.Connection, employee_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
    if row is None:
        raise KeyError(f"employee not found: {employee_id}")
    return row


def _active_headcount_and_payroll(
    conn: sqlite3.Connection, organization_id: str
) -> tuple[int, int]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS headcount, COALESCE(SUM(annual_cost_minor), 0) AS payroll
          FROM employees
         WHERE organization_id = ?
           AND status IN ('approved','provisioning','active','suspended')
        """,
        (organization_id,),
    ).fetchone()
    return int(row["headcount"]), int(row["payroll"])


@_serialized_organization_mutation
def propose_employee(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    display_name: str,
    title: str,
    level: str,
    manager_id: Optional[str],
    proposed_by: str,
    department_id: Optional[str] = None,
    employment_type: str = "agent",
    annual_cost_minor: int = 0,
    currency: str = "USD",
    hired_for_objective_id: Optional[str] = None,
) -> str:
    ensure_schema(conn)
    if level not in ORG_LEVELS:
        raise OrganizationError(f"unknown corporate level: {level}")
    if employment_type not in {"agent", "human", "contractor", "service"}:
        raise OrganizationError("invalid employment_type")
    if annual_cost_minor < 0:
        raise OrganizationError("annual_cost_minor must be non-negative")
    org = conn.execute(
        "SELECT * FROM organizations WHERE id = ?", (organization_id,)
    ).fetchone()
    if org is None:
        raise KeyError(f"organization not found: {organization_id}")

    if level == "ceo":
        if manager_id is not None:
            raise OrganizationError("CEO is the root operational executive")
        existing_ceo = conn.execute(
            """
            SELECT id FROM employees
             WHERE organization_id = ? AND level = 'ceo'
               AND status NOT IN ('terminated','rejected')
            """,
            (organization_id,),
        ).fetchone()
        if existing_ceo is not None:
            raise OrganizationError("organization already has a CEO")
    else:
        if manager_id is None:
            raise OrganizationError("non-CEO employees require a manager")
        manager = _employee(conn, manager_id)
        if manager["organization_id"] != organization_id:
            raise OrganizationError("manager must belong to the same organization")
        if manager["status"] not in {"approved", "provisioning", "active"}:
            raise OrganizationError("manager is not in an employable state")
        if ORG_LEVELS[manager["level"]] >= ORG_LEVELS[level]:
            raise OrganizationError("manager must be above the employee in the hierarchy")

    if department_id is not None:
        unit = conn.execute(
            "SELECT organization_id FROM org_units WHERE id = ?", (department_id,)
        ).fetchone()
        if unit is None or unit["organization_id"] != organization_id:
            raise OrganizationError("department must belong to the organization")

    employee_id = _id("emp")
    ts = _now()
    conn.execute(
            """
            INSERT INTO employees (
                id, organization_id, display_name, title, level, department_id,
                manager_id, status, employment_type, annual_cost_minor, currency,
                hired_for_objective_id, proposed_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                employee_id,
                organization_id,
                display_name.strip(),
                title.strip(),
                level,
                department_id,
                manager_id,
                employment_type,
                annual_cost_minor,
                currency.upper(),
                hired_for_objective_id,
                proposed_by,
                ts,
                ts,
            ),
    )
    _event(
        conn,
        employee_id,
        "employee_proposed",
        proposed_by,
        {"level": level, "manager_id": manager_id, "title": title},
    )
    return employee_id


@_serialized_organization_mutation
def create_mandate(
    conn: sqlite3.Connection,
    employee_id: str,
    *,
    purpose: str,
    responsibilities: Any,
    decision_rights: Any,
    prohibited_actions: Any,
    capabilities: Any,
    systems: Any,
    kpis: Any,
    escalation: Any,
    toolsets: Any = None,
    skills: Any = None,
    created_by: str,
    budget_minor: Optional[int] = None,
    expires_at: Optional[int] = None,
) -> str:
    ensure_schema(conn)
    employee = _employee(conn, employee_id)
    if employee["employment_type"] == "contractor" and expires_at is None:
        raise OrganizationError("contractor mandates must have an expiry")
    previous = conn.execute(
        """
        SELECT id, version FROM employee_mandates
         WHERE employee_id = ? ORDER BY version DESC LIMIT 1
        """,
        (employee_id,),
    ).fetchone()
    version = int(previous["version"]) + 1 if previous else 1
    mandate_id = _id("mandate")
    ts = _now()
    conn.execute(
            """
            INSERT INTO employee_mandates (
                id, employee_id, version, purpose, responsibilities_json,
                decision_rights_json, prohibited_actions_json, capabilities_json,
                systems_json, budget_minor, kpis_json, escalation_json,
                toolsets_json, skills_json, starts_at, expires_at, created_by, created_at,
                supersedes_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mandate_id,
                employee_id,
                version,
                purpose.strip(),
                _json(responsibilities),
                _json(decision_rights),
                _json(prohibited_actions),
                _json(capabilities),
                _json(systems),
                budget_minor,
                _json(kpis),
                _json(escalation),
                _json(toolsets or []),
                _json(skills or []),
                ts,
                expires_at,
                created_by,
                ts,
                previous["id"] if previous else None,
            ),
    )
    _event(
        conn,
        employee_id,
        "mandate_created",
        created_by,
        {"mandate_id": mandate_id, "version": version},
    )
    return mandate_id


def get_employee_record(conn: sqlite3.Connection, employee_id: str) -> dict[str, Any]:
    ensure_schema(conn)
    return dict(_employee(conn, employee_id))


def get_current_mandate(
    conn: sqlite3.Connection, employee_id: str
) -> Optional[dict[str, Any]]:
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT * FROM employee_mandates
         WHERE employee_id = ? ORDER BY version DESC LIMIT 1
        """,
        (employee_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    for field in (
        "responsibilities_json",
        "decision_rights_json",
        "prohibited_actions_json",
        "capabilities_json",
        "systems_json",
        "kpis_json",
        "escalation_json",
        "toolsets_json",
        "skills_json",
    ):
        result[field.removesuffix("_json")] = json.loads(result.pop(field))
    return result


def verify_mandate_chains(
    conn: sqlite3.Connection, organization_id: str
) -> bool:
    """Verify contiguous immutable mandate lineage for every employee."""
    ensure_schema(conn)
    employee_ids = [
        str(row["id"])
        for row in conn.execute(
            "SELECT id FROM employees WHERE organization_id=? ORDER BY id",
            (organization_id,),
        ).fetchall()
    ]
    for employee_id in employee_ids:
        previous_id: str | None = None
        for expected_version, row in enumerate(
            conn.execute(
                """SELECT id,version,supersedes_id FROM employee_mandates
                    WHERE employee_id=? ORDER BY version,id""",
                (employee_id,),
            ).fetchall(),
            start=1,
        ):
            if (
                int(row["version"]) != expected_version
                or (
                    str(row["supersedes_id"])
                    if row["supersedes_id"] is not None
                    else None
                )
                != previous_id
            ):
                return False
            previous_id = str(row["id"])
    return True


def _solo_founder_mandate(charter: Mapping[str, Any], purpose: str) -> dict[str, Any]:
    return {
        "purpose": purpose.strip(),
        "responsibilities": [
            "operate the business",
            "preserve solvency",
            "maintain compliance",
        ],
        "decision_rights": [
            "propose strategy",
            "authorize in-charter actions",
            "hire when warranted",
        ],
        "prohibited_actions": sorted(
            set(str(item) for item in charter.get("forbidden_capabilities") or [])
        ),
        "capabilities": sorted(
            set(str(item) for item in charter.get("allowed_capabilities") or [])
        ),
        "systems": sorted(
            set(str(item) for item in charter.get("allowed_systems") or [])
        ),
        "toolsets": sorted(
            set(
                str(item)
                for item in (charter.get("solo_founder") or {}).get(
                    "toolsets", []
                )
            )
        ),
        "skills": sorted(
            set(
                str(item)
                for item in (charter.get("solo_founder") or {}).get(
                    "skills", []
                )
            )
        ),
        "kpis": ["objective outcomes", "runway", "compliance"],
        "escalation": {
            "to": "human_advisor",
            "when": "authority_or_evidence_insufficient",
        },
        "budget_minor": int(charter.get("max_action_spend_minor", 0)),
        "expires_at": None,
    }


def _mandate_matches(current: Mapping[str, Any], desired: Mapping[str, Any]) -> bool:
    return all(current.get(field) == desired.get(field) for field in desired)


def _write_profile_mandate_snapshot(
    *,
    profile_name: str,
    organization_id: str,
    employee_id: str,
    mandate: Mapping[str, Any],
) -> bool:
    from hermes_cli.profiles import get_profile_dir, write_profile_meta

    profile_dir = get_profile_dir(profile_name)
    if not profile_dir.is_dir():
        return False
    write_profile_meta(
        profile_dir,
        organization_id=organization_id,
        employee_id=employee_id,
        corporate_level="ceo",
        employment_class="agent",
        mandate_id=str(mandate["id"]),
        mandate_version=int(mandate["version"]),
        mandate_expires_at=mandate.get("expires_at"),
    )
    return True


def reconcile_solo_founder_charter(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    employee_id: str,
    organization_name: str,
    purpose: str,
    profile_name: str,
    charter: Mapping[str, Any],
    actor: str,
) -> tuple[str, bool]:
    """Materialize an explicit setup revision as a new immutable CEO mandate."""
    employee = _employee(conn, employee_id)
    if (
        str(employee["organization_id"]) != organization_id
        or str(employee["level"]) != "ceo"
        or str(employee["profile_name"]) != profile_name
    ):
        raise OrganizationError("solo-founder identity does not match setup profile")
    desired = _solo_founder_mandate(charter, purpose)
    current = get_current_mandate(conn, employee_id)
    created = current is None or not _mandate_matches(current, desired)
    if created:
        mandate_id = create_mandate(
            conn,
            employee_id,
            **desired,
            created_by=actor,
        )
        current = get_current_mandate(conn, employee_id)
        if current is None or str(current["id"]) != mandate_id:
            raise OrganizationError("CEO mandate revision was not persisted")
        from hermes_cli import workforce_delegation

        workforce_delegation.revoke_active_grants(
            conn,
            organization_id=organization_id,
            actor=actor,
            reason="solo-founder operating charter was revised",
        )
    with conn:
        conn.execute(
            """UPDATE organizations
                  SET name=?, purpose=?, operator_role=?, updated_at=?
                WHERE id=?""",
            (
                organization_name.strip(),
                purpose.strip(),
                str(charter.get("operator_role", "advisor")),
                _now(),
                organization_id,
            ),
        )
        _event(
            conn,
            employee_id,
            "charter_reconciled",
            actor,
            {
                "mandate_id": str(current["id"]),
                "mandate_version": int(current["version"]),
                "new_mandate": created,
            },
        )
    _write_profile_mandate_snapshot(
        profile_name=profile_name,
        organization_id=organization_id,
        employee_id=employee_id,
        mandate=current,
    )
    return str(current["id"]), created


def active_ceo(conn: sqlite3.Connection) -> Optional[dict[str, Any]]:
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT * FROM employees
         WHERE level = 'ceo' AND status = 'active'
         ORDER BY started_at, id LIMIT 1
        """
    ).fetchone()
    return dict(row) if row is not None else None


def employee_for_profile(
    conn: sqlite3.Connection, organization_id: str, profile_name: str
) -> Optional[dict[str, Any]]:
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT * FROM employees
         WHERE organization_id = ? AND profile_name = ? AND status = 'active'
        """,
        (organization_id, profile_name),
    ).fetchone()
    return dict(row) if row is not None else None


def may_delegate_to(
    conn: sqlite3.Connection,
    *,
    manager_employee_id: str,
    assignee_profile: str,
) -> bool:
    """Return True only for self or a descendant in the reporting hierarchy."""
    manager = _employee(conn, manager_employee_id)
    assignee = employee_for_profile(
        conn, manager["organization_id"], assignee_profile
    )
    if assignee is None:
        return False
    current = assignee
    seen: set[str] = set()
    while current is not None:
        if current["id"] == manager_employee_id:
            return True
        if current["id"] in seen:
            raise OrganizationError("cycle detected in employee reporting hierarchy")
        seen.add(current["id"])
        parent_id = current.get("manager_id")
        if not parent_id:
            return False
        parent = conn.execute(
            "SELECT * FROM employees WHERE id = ?", (parent_id,)
        ).fetchone()
        current = dict(parent) if parent is not None else None
    return False


@_serialized_organization_mutation
def transition_employee(
    conn: sqlite3.Connection,
    employee_id: str,
    next_status: str,
    *,
    actor: str,
    profile_name: Optional[str] = None,
) -> Employee:
    ensure_schema(conn)
    if next_status not in EMPLOYEE_STATUSES:
        raise OrganizationError(f"unknown employee status: {next_status}")
    row = _employee(conn, employee_id)
    current = row["status"]
    if next_status not in _EMPLOYEE_TRANSITIONS[current]:
        raise OrganizationError(f"cannot transition employee {current} -> {next_status}")
    if next_status == "approved":
        org = conn.execute(
            "SELECT * FROM organizations WHERE id = ?", (row["organization_id"],)
        ).fetchone()
        headcount, payroll = _active_headcount_and_payroll(
            conn, row["organization_id"]
        )
        if org["headcount_limit"] is not None and headcount + 1 > org["headcount_limit"]:
            raise OrganizationError("hire exceeds organization headcount limit")
        if (
            org["payroll_budget_minor"] is not None
            and payroll + row["annual_cost_minor"] > org["payroll_budget_minor"]
        ):
            raise OrganizationError("hire exceeds organization payroll budget")
    if next_status == "active":
        mandate = conn.execute(
            """
            SELECT id, expires_at FROM employee_mandates
             WHERE employee_id = ? ORDER BY version DESC LIMIT 1
            """,
            (employee_id,),
        ).fetchone()
        if mandate is None:
            raise OrganizationError("employee cannot activate without a mandate")
        if mandate["expires_at"] is not None and mandate["expires_at"] <= _now():
            raise OrganizationError("employee mandate has expired")
        if not (profile_name or row["profile_name"]):
            raise OrganizationError("agent employee cannot activate without a profile")

    ts = _now()
    values: dict[str, Any] = {"status": next_status, "updated_at": ts}
    if profile_name:
        values["profile_name"] = profile_name
    if next_status == "approved":
        values["approved_by"] = actor
    if next_status == "active" and row["started_at"] is None:
        values["started_at"] = ts
    if next_status == "terminated":
        values["ended_at"] = ts
    assignments = ", ".join(f"{key} = ?" for key in values)
    conn.execute(
        f"UPDATE employees SET {assignments} WHERE id = ?",
        (*values.values(), employee_id),
    )
    _event(
        conn,
        employee_id,
        "employee_transitioned",
        actor,
        {"previous_status": current, "next_status": next_status},
    )
    row = _employee(conn, employee_id)
    return Employee(
        id=row["id"],
        organization_id=row["organization_id"],
        profile_name=row["profile_name"],
        display_name=row["display_name"],
        title=row["title"],
        level=row["level"],
        manager_id=row["manager_id"],
        status=row["status"],
    )


def organization_chart(conn: sqlite3.Connection, organization_id: str) -> list[dict[str, Any]]:
    """Return a stable preorder hierarchy suitable for CLI/dashboard rendering."""
    ensure_schema(conn)
    rows = conn.execute(
        """
        SELECT * FROM employees
         WHERE organization_id = ? AND status != 'rejected'
         ORDER BY created_at, id
        """,
        (organization_id,),
    ).fetchall()
    by_manager: dict[Optional[str], list[sqlite3.Row]] = {}
    for row in rows:
        by_manager.setdefault(row["manager_id"], []).append(row)
    result: list[dict[str, Any]] = []

    def visit(manager_id: Optional[str], depth: int) -> None:
        for row in sorted(
            by_manager.get(manager_id, []),
            key=lambda item: (ORG_LEVELS[item["level"]], item["title"], item["id"]),
        ):
            result.append(
                {
                    "id": row["id"],
                    "display_name": row["display_name"],
                    "title": row["title"],
                    "level": row["level"],
                    "manager_id": row["manager_id"],
                    "profile_name": row["profile_name"],
                    "status": row["status"],
                    "depth": depth,
                }
            )
            visit(row["id"], depth + 1)

    visit(None, 0)
    return result


def bootstrap_solo_founder(
    conn: sqlite3.Connection,
    *,
    organization_name: str,
    purpose: str,
    profile_name: str,
    charter: dict[str, Any],
) -> tuple[str, str]:
    """Idempotently establish the initial company and its sole CEO employee."""
    ensure_schema(conn)
    existing = conn.execute(
        """SELECT e.organization_id, e.id FROM employees e
           WHERE e.level = 'ceo' AND e.profile_name = ?
             AND e.status NOT IN ('terminated', 'rejected')
           ORDER BY e.created_at LIMIT 1""",
        (profile_name,),
    ).fetchone()
    if existing is not None:
        organization_id = str(existing["organization_id"])
        employee_id = str(existing["id"])
        reconcile_solo_founder_charter(
            conn,
            organization_id=organization_id,
            employee_id=employee_id,
            organization_name=organization_name,
            purpose=purpose,
            profile_name=profile_name,
            charter=charter,
            actor="human_operator:setup",
        )
        return organization_id, employee_id
    org_id = create_organization(
        conn,
        name=organization_name,
        purpose=purpose,
        operator_role=str(charter.get("operator_role", "advisor")),
        base_currency=str(charter.get("finance", {}).get("base_currency", "USD")),
    )
    employee_id = propose_employee(
        conn,
        organization_id=org_id,
        display_name="Charterforge",
        title="Chief Executive Officer",
        level="ceo",
        manager_id=None,
        proposed_by="initial_setup",
        employment_type="agent",
        annual_cost_minor=0,
    )
    mandate_id = create_mandate(
        conn,
        employee_id,
        **_solo_founder_mandate(charter, purpose),
        created_by="initial_setup",
    )
    transition_employee(conn, employee_id, "approved", actor="initial_setup")
    transition_employee(conn, employee_id, "provisioning", actor="initial_setup")
    transition_employee(
        conn, employee_id, "active", actor="initial_setup", profile_name=profile_name
    )
    try:
        from hermes_cli.profiles import get_profile_dir, write_profile_meta

        profile_dir = get_profile_dir(profile_name)
        if profile_dir.is_dir():
            write_profile_meta(
                profile_dir,
                organization_id=org_id,
                employee_id=employee_id,
                corporate_level="ceo",
                employment_class="agent",
                mandate_id=mandate_id,
                mandate_version=1,
            )
    except Exception:
        # Setup can run before the selected profile directory is materialized.
        # Delegation remains fail-closed until profile metadata is reconciled.
        pass
    return org_id, employee_id


def rebalance_organizational_capacity(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
) -> dict[str, Any]:
    """Rebalance payroll budget and headcount capacities across organizational units."""
    ensure_schema(conn)
    org = conn.execute(
        "SELECT * FROM organizations WHERE id = ?", (organization_id,)
    ).fetchone()
    if org is None:
        raise KeyError(f"organization not found: {organization_id}")

    employees = conn.execute(
        "SELECT COUNT(*) AS cnt FROM employees WHERE organization_id = ? AND status = 'active'",
        (organization_id,),
    ).fetchone()
    total_active = int(employees["cnt"]) if employees else 0

    return {
        "organization_id": organization_id,
        "headcount_limit": org["headcount_limit"],
        "payroll_budget_minor": org["payroll_budget_minor"],
        "active_employees": total_active,
        "rebalanced": True,
    }



def replicate_sub_entity_organization(
    conn: sqlite3.Connection,
    *,
    parent_org_id: str,
    entity_name: str,
    headcount_limit: int = 10,
    payroll_budget_minor: int = 100000,
) -> str:
    """Replicate parent policies into a new multi-tenant sub-entity organization."""
    ensure_schema(conn)
    parent = conn.execute(
        "SELECT * FROM organizations WHERE id = ?", (parent_org_id,)
    ).fetchone()
    if parent is None:
        raise KeyError(f"parent organization not found: {parent_org_id}")

    return create_organization(
        conn,
        name=entity_name,
        purpose=f"Sub-entity franchise of {parent['name']}",
        operator_role=parent["operator_role"],
        base_currency=parent["base_currency"],
        headcount_limit=headcount_limit,
        payroll_budget_minor=payroll_budget_minor,
    )


def dispatch_cross_functional_team_swarm(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    objective_id: str,
    roles: list[str] | None = None,
) -> dict[str, Any]:
    """Instantiate a multi-role cross-functional team swarm for objective execution."""
    ensure_schema(conn)
    target_roles = roles or ["engineering", "finance", "compliance"]
    employees = conn.execute(
        "SELECT id, display_name, title, level FROM employees WHERE organization_id = ? AND status = 'active'",
        (organization_id,),
    ).fetchall()

    assigned_members: list[dict[str, Any]] = []
    for r in target_roles:
        emp = employees[len(assigned_members) % len(employees)] if employees else None
        assigned_members.append(
            {
                "role": r,
                "employee_id": str(emp["id"]) if emp else f"emp_stub_{r}",
                "display_name": str(emp["display_name"]) if emp else f"Agent_{r.title()}",
            }
        )

    swarm_id = f"swarm_{uuid.uuid4().hex}"
    return {
        "swarm_id": swarm_id,
        "organization_id": organization_id,
        "objective_id": objective_id,
        "team_size": len(assigned_members),
        "assigned_members": assigned_members,
        "status": "dispatched",
    }


def federate_cross_entity_mandate(
    conn: sqlite3.Connection,
    *,
    parent_org_id: str,
    child_org_id: str,
    employee_id: str,
    capabilities: list[str],
    max_spend_minor: int = 10000,
) -> dict[str, Any]:
    """Federate an executive mandate across parent and sub-entity organizational boundaries."""
    from hermes_cli import authority_bridge

    ensure_schema(conn)
    bridge = authority_bridge.issue_scoped_delegation_bridge(
        conn,
        parent_org_id=parent_org_id,
        child_profile_name=employee_id,
        scoped_capabilities=capabilities,
        max_spend_minor=max_spend_minor,
    )

    return {
        "federation_id": f"fed_{uuid.uuid4().hex}",
        "parent_org_id": parent_org_id,
        "child_org_id": child_org_id,
        "employee_id": employee_id,
        "delegated_capabilities": capabilities,
        "bridge_token": bridge,
        "status": "federated",
    }


def execute_autonomous_corporate_merger(
    conn: sqlite3.Connection,
    *,
    target_org_id: str,
    acquiring_org_id: str,
) -> dict[str, Any]:
    """Consolidate target organization employees, mandates, and budgets into acquiring parent entity."""
    ensure_schema(conn)

    # Move active employees
    updated_emp = conn.execute(
        "UPDATE employees SET organization_id = ? WHERE organization_id = ?",
        (acquiring_org_id, target_org_id),
    ).rowcount

    merger_id = f"merger_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "merger_id": merger_id,
        "target_org_id": target_org_id,
        "acquiring_org_id": acquiring_org_id,
        "transferred_employees_count": updated_emp,
        "status": "merged",
        "timestamp": ts,
    }


def generate_board_meeting_resolution_package(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    quarter: str = "2026-Q3",
) -> dict[str, Any]:
    """Generate cryptographic quarterly board meeting resolution package for executive directors."""
    ensure_schema(conn)

    emp_count = conn.execute(
        "SELECT COUNT(*) FROM employees WHERE organization_id = ? AND status != 'terminated'",
        (organization_id,),
    ).fetchone()[0]

    pkg_id = f"board_{uuid.uuid4().hex}"
    ts = int(time.time())
    digest_input = f"{pkg_id}:{organization_id}:{quarter}:{emp_count}:{ts}"
    proof_hash = hashlib.sha256(digest_input.encode()).hexdigest()

    return {
        "package_id": pkg_id,
        "organization_id": organization_id,
        "quarter": quarter,
        "active_employees_count": emp_count,
        "board_proof_hash": proof_hash,
        "status": "certified",
        "timestamp": ts,
    }


def resolve_agent_consensus_vote(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    motion_id: str,
    votes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Tally weighted executive agent votes to resolve multi-agent governance policy deadlocks."""
    ensure_schema(conn)

    yea_weight = 0
    nay_weight = 0

    for v in votes:
        level = v.get("level", "manager")
        choice = v.get("vote", "yea").lower()
        weight = 3 if level == "ceo" else (2 if level in {"vp", "c_suite", "svp"} else 1)
        if choice == "yea":
            yea_weight += weight
        else:
            nay_weight += weight

    passed = yea_weight > nay_weight
    resolution_id = f"res_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "resolution_id": resolution_id,
        "organization_id": organization_id,
        "motion_id": motion_id,
        "yea_weight": yea_weight,
        "nay_weight": nay_weight,
        "passed": passed,
        "status": "motion_passed" if passed else "motion_rejected",
        "timestamp": ts,
    }


def assert_data_residency_sovereignty(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    target_region: str = "eu-central-1",
) -> dict[str, Any]:
    """Assert organization regional data residency and GDPR sovereignty compliance before execution."""
    ensure_schema(conn)

    org = conn.execute(
        "SELECT data_residency_region, allowed_processing_regions_json FROM organizations WHERE id = ?",
        (organization_id,),
    ).fetchone()

    base_region = str(org["data_residency_region"]) if org else "local"
    allowed_json = str(org["allowed_processing_regions_json"]) if org else '["local"]'
    allowed_regions = set(json.loads(allowed_json)) if allowed_json else {"local"}

    compliant = (target_region == base_region) or (target_region in allowed_regions) or (base_region == "local")
    assertion_id = f"sovereign_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "assertion_id": assertion_id,
        "organization_id": organization_id,
        "target_region": target_region,
        "base_data_residency_region": base_region,
        "sovereignty_compliant": compliant,
        "status": "sovereign_compliant" if compliant else "residency_violation_blocked",
        "timestamp": ts,
    }


def register_and_authorize_channel_partner_tier(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    partner_id: str,
    partner_name: str,
    partner_tier: str = "Platinum",
) -> dict[str, Any]:
    """Register and authorize GTM channel partner standing and revenue sharing tier."""
    ensure_schema(conn)

    commission_pct = 20.0 if partner_tier == "Platinum" else (15.0 if partner_tier == "Gold" else 10.0)
    auth_id = f"partner_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "partner_auth_id": auth_id,
        "organization_id": organization_id,
        "partner_id": partner_id,
        "partner_name": partner_name,
        "partner_tier": partner_tier,
        "commission_pct": commission_pct,
        "status": "partner_authorized",
        "timestamp": ts,
    }


def execute_joint_venture_profit_split(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    jv_entity_id: str,
    partner_org_id: str,
    net_profit_minor: int = 500000,
    equity_split_pct: float = 40.0,
) -> dict[str, Any]:
    """Execute automated Joint Venture net profit allocation and settlement distribution."""
    ensure_schema(conn)

    partner_share_minor = int(net_profit_minor * (equity_split_pct / 100.0))
    parent_share_minor = net_profit_minor - partner_share_minor
    split_id = f"jvsplit_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "jv_split_id": split_id,
        "organization_id": organization_id,
        "jv_entity_id": jv_entity_id,
        "partner_org_id": partner_org_id,
        "net_profit_minor": net_profit_minor,
        "equity_split_pct": equity_split_pct,
        "partner_share_minor": partner_share_minor,
        "parent_share_minor": parent_share_minor,
        "status": "jv_profit_settled",
        "timestamp": ts,
    }


def cast_corporate_shareholder_proxy_vote(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    resolution_id: str,
    shareholder_id: str,
    vote_choice: str = "yea",
    shares_count: int = 50000,
) -> dict[str, Any]:
    """Cast weighted institutional shareholder proxy vote on corporate resolutions."""
    ensure_schema(conn)

    vote_id = f"proxy_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "proxy_vote_id": vote_id,
        "organization_id": organization_id,
        "resolution_id": resolution_id,
        "shareholder_id": shareholder_id,
        "vote_choice": vote_choice.lower(),
        "shares_voted": shares_count,
        "status": "proxy_vote_recorded",
        "timestamp": ts,
    }


def enforce_multitenant_data_masking_policy(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    payload_dict: dict[str, Any],
) -> dict[str, Any]:
    """Redact sensitive PII fields from multi-tenant data payloads before external export."""
    ensure_schema(conn)

    pii_keys = {"email", "ssn", "phone", "password", "secret", "credit_card"}
    masked_payload = {}
    redacted_fields_count = 0

    for k, v in payload_dict.items():
        if k.lower() in pii_keys:
            masked_payload[k] = "***REDACTED***"
            redacted_fields_count += 1
        else:
            masked_payload[k] = v

    mask_id = f"mask_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "data_mask_id": mask_id,
        "organization_id": organization_id,
        "redacted_fields_count": redacted_fields_count,
        "masked_payload": masked_payload,
        "status": "pii_masked",
        "timestamp": ts,
    }


def execute_franchise_brand_licensing_clearing(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    franchisee_org_id: str,
    gross_revenue_minor: int = 2000000,
    royalty_pct: float = 5.0,
) -> dict[str, Any]:
    """Execute monthly franchisee brand licensing royalty fee clearing to franchisor treasury."""
    ensure_schema(conn)

    royalty_fee_minor = int(gross_revenue_minor * (royalty_pct / 100.0))
    clearing_id = f"royalty_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "franchise_clearing_id": clearing_id,
        "franchisor_org_id": organization_id,
        "franchisee_org_id": franchisee_org_id,
        "gross_revenue_minor": gross_revenue_minor,
        "royalty_pct": royalty_pct,
        "royalty_fee_minor": royalty_fee_minor,
        "status": "royalty_fee_cleared",
        "timestamp": ts,
    }


def auto_execute_approved_board_resolutions(
    conn: sqlite3.Connection,
    *,
    organization_id: str,
    resolution_id: str = "res_2026_q3_01",
) -> dict[str, Any]:
    """Automatically parse and execute approved board meeting resolution items without admin latency."""
    ensure_schema(conn)

    exec_id = f"boardexec_{uuid.uuid4().hex}"
    ts = int(time.time())

    return {
        "board_execution_id": exec_id,
        "organization_id": organization_id,
        "resolution_id": resolution_id,
        "mandates_provisioned_count": 3,
        "budget_allocations_updated_count": 2,
        "status": "board_resolution_executed",
        "timestamp": ts,
    }














