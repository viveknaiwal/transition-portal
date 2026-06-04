# Employee data layer — fetches from Darwinbox APIs with 1-hour Streamlit cache.
# No Google Sheet dependency. Data is always fresh (max 1 hour old).

import streamlit as st
from lib.darwinbox import fetch_employee_master


@st.cache_data(ttl=3600, show_spinner="Loading employee data…")
def get_all_employees_cached() -> list[dict]:
    """
    Fetches all employees from Darwinbox master + payroll CTC APIs.
    Cached for 1 hour — refreshes automatically, no manual sync needed.
    Includes: active employees + those who left after 31 March 2026.
    """
    return fetch_employee_master()


def get_employees_for_manager(manager_email: str) -> list[dict]:
    """Active direct reports for a given manager email."""
    email = manager_email.lower().strip()
    return [
        e for e in get_all_employees_cached()
        if e.get("l1_manager_email", "").lower() == email
        and str(e.get("employee_status", "")).lower() == "active"
    ]


def get_employee_by_code(emp_code: str) -> dict | None:
    for e in get_all_employees_cached():
        if e.get("emp_code") == emp_code:
            return e
    return None


def get_employee_count() -> int:
    try:
        return len(get_all_employees_cached())
    except Exception:
        return 0
