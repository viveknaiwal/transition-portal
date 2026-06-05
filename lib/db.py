import uuid
from datetime import datetime, timezone
from supabase import create_client, Client
from lib.config import get_secret

_client: Client | None = None

SEPARATION_REASONS = [
    "Business Conditions",
    "Performance Issues",
]

SUB_REASONS = {
    "Business Conditions": [
        "Role Redundancy",
        "Location Decommissioned",
        "Business Closure",
        "Cost Optimization",
    ],
    "Performance Issues": [
        "PIP Unsuccessful",
        "Probation Unsuccessful",
    ],
}

COMMUNICATION_STATUSES = ["Pending", "Hold", "Completed"]

CASE_STATUSES = ["Pending", "Hold", "Submitted", "Sent Back", "Admin Closed"]

ADMIN_ACTIONS = ["Closed", "Sent Back"]


def get_client() -> Client:
    global _client
    if _client is None:
        url = get_secret("SUPABASE_URL")
        key = get_secret("SUPABASE_ANON_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in secrets")
        _client = create_client(url, key)
    return _client


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Auth / User Roles ──────────────────────────────────────────────────────────

def get_user_role(email: str) -> str | None:
    sb = get_client()
    res = sb.table("user_roles").select("role").eq("email", email.lower()).eq("active", True).execute()
    if res.data:
        return res.data[0]["role"]
    # Auto-detect manager: their email appears as l1_manager_email for at least one active employee
    res2 = sb.table("employees").select("employee_id").eq("l1_manager_email", email.lower()).limit(1).execute()
    if res2.data:
        return "MANAGER"
    return None


def get_all_user_roles() -> list:
    sb = get_client()
    return sb.table("user_roles").select("*").order("created_at", desc=True).execute().data or []


def upsert_user_role(email: str, role: str):
    sb = get_client()
    sb.table("user_roles").upsert(
        {"email": email.lower(), "role": role, "active": True},
        on_conflict="email",
    ).execute()


def deactivate_user_role(row_id: str):
    sb = get_client()
    sb.table("user_roles").update({"active": False}).eq("id", row_id).execute()


# ── Employees ──────────────────────────────────────────────────────────────────

def upsert_employees(employees: list[dict]) -> int:
    sb    = get_client()
    now   = _now()
    total = 0
    for i in range(0, len(employees), 200):
        batch = [{**e, "synced_at": now} for e in employees[i : i + 200]]
        sb.table("employees").upsert(batch, on_conflict="employee_id").execute()
        total += len(batch)
    return total


def get_employees_for_manager(manager_email: str) -> list:
    sb = get_client()
    return (
        sb.table("employees")
        .select("*")
        .eq("l1_manager_email", manager_email.lower())
        .eq("employee_status", "Active")
        .order("full_name")
        .execute()
        .data or []
    )


def get_employee(emp_code: str) -> dict | None:
    sb  = get_client()
    res = sb.table("employees").select("*").eq("emp_code", emp_code).execute()
    return res.data[0] if res.data else None


def get_all_employees() -> list:
    sb = get_client()
    return sb.table("employees").select("*").order("full_name").execute().data or []


def get_employee_count() -> int:
    sb  = get_client()
    res = sb.table("employees").select("employee_id", count="exact").execute()
    return res.count or 0


# ── Cases ──────────────────────────────────────────────────────────────────────

def _gen_case_id(emp_code: str) -> str:
    sb     = get_client()
    res    = sb.table("cases").select("case_id", count="exact").eq("emp_code", emp_code).execute()
    serial = (res.count or 0) + 1
    return f"C24-{emp_code}-{serial:04d}"


def create_case(data: dict) -> dict:
    sb       = get_client()
    emp_code = str(data.get("emp_code", "00000"))
    data     = {**data, "case_id": _gen_case_id(emp_code), "created_at": _now(), "updated_at": _now()}
    res      = sb.table("cases").insert(data).execute()
    return res.data[0] if res.data else {}


def update_case(case_id: str, updates: dict) -> dict:
    sb  = get_client()
    res = sb.table("cases").update({**updates, "updated_at": _now()}).eq("case_id", case_id).execute()
    return res.data[0] if res.data else {}


def get_case(case_id: str) -> dict | None:
    sb  = get_client()
    res = sb.table("cases").select("*").eq("case_id", case_id).execute()
    return res.data[0] if res.data else None


def get_cases_for_manager(manager_email: str) -> list:
    sb = get_client()
    return (
        sb.table("cases")
        .select("*")
        .eq("l1_manager_email", manager_email.lower())
        .order("created_at", desc=True)
        .execute()
        .data or []
    )


def get_all_cases(status_filter: str = "", entity_filter: str = "") -> list:
    sb    = get_client()
    query = sb.table("cases").select("*").order("created_at", desc=True)
    if status_filter:
        query = query.eq("status", status_filter)
    if entity_filter:
        query = query.eq("entity", entity_filter)
    return query.execute().data or []


def get_fnf_ready_cases() -> list:
    sb = get_client()
    return (
        sb.table("cases")
        .select("*")
        .eq("closure_status", "Closed")
        .order("last_working_date")
        .execute()
        .data or []
    )


# ── Audit ──────────────────────────────────────────────────────────────────────

def log_audit(action: str, case_id: str, user_email: str, remarks: str = ""):
    sb = get_client()
    sb.table("audit_log").insert({
        "action":     action,
        "case_id":    case_id,
        "user_email": user_email,
        "remarks":    remarks,
        "created_at": _now(),
    }).execute()


def get_audit_log(case_id: str) -> list:
    sb = get_client()
    return (
        sb.table("audit_log")
        .select("*")
        .eq("case_id", case_id)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
