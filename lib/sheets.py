# Employee data layer.
# Admin "Force Refresh" → fetches from Darwinbox API → writes to Supabase.
# All managers read from Supabase (instant DB query, no API call).

from lib.db import get_client


def get_employees_for_manager(manager_email: str) -> list[dict]:
    """Instant DB read from Supabase employees table."""
    sb  = get_client()
    res = (
        sb.table("employees")
        .select("*")
        .eq("l1_manager_email", manager_email.lower().strip())
        .eq("employee_status", "Active")
        .order("full_name")
        .execute()
    )
    return res.data or []


def get_employee_by_code(emp_code: str) -> dict | None:
    sb  = get_client()
    res = sb.table("employees").select("*").eq("emp_code", emp_code).execute()
    return res.data[0] if res.data else None


def get_employee_count() -> int:
    sb  = get_client()
    res = sb.table("employees").select("employee_id", count="exact").execute()
    return res.count or 0
