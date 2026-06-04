import os
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from lib.db import (
    get_all_cases, get_case, update_case, log_audit,
    get_all_user_roles, upsert_user_role, deactivate_user_role,
    get_audit_log, get_employee_count, ADMIN_ACTIONS,
)
from views.manager_view import render_my_team, render_my_cases


def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Case detail dialog ─────────────────────────────────────────────────────────

@st.dialog("Case — Admin View", width="large")
def _show_case_detail(case_id: str, admin_email: str):
    case = get_case(case_id)
    if not case:
        st.error("Case not found.")
        return
    c = case

    st.markdown(f"### {c['case_id']} — {c.get('emp_name','')}")
    st.caption(
        f"Status: **{c.get('status','')}** &nbsp;|&nbsp; "
        f"Closure: **{c.get('closure_status') or '—'}** &nbsp;|&nbsp; "
        f"LWD: {c.get('last_working_date','')} &nbsp;|&nbsp; "
        f"By: {c.get('created_by','')}"
    )
    st.divider()

    info_tab, calc_tab, audit_tab = st.tabs(["Details", "FNF Calculations", "Audit Log"])

    with info_tab:
        cc1, cc2 = st.columns(2)
        with cc1:
            st.write(f"**Emp Code:** {c.get('emp_code','')}")
            st.write(f"**Entity / BU:** {c.get('entity','')} / {c.get('business_unit','')}")
            st.write(f"**Grade / Band:** {c.get('grade','')} / {c.get('band','')}")
            st.write(f"**Designation:** {c.get('external_designation','')}")
            st.write(f"**DOJ / Group DOJ:** {c.get('doj','')} / {c.get('group_doj','')}")
            st.write(f"**Date of Resignation:** {c.get('date_of_resignation','')}")
            st.write(f"**Last Working Date:** {c.get('last_working_date','')}")
        with cc2:
            st.write(f"**Separation Reason:** {c.get('separation_reason','')}")
            st.write(f"**Sub Reason:** {c.get('separation_sub_reason','')}")
            st.write(f"**Notice Type:** {c.get('immediate_exit_or_serving_notice','')}")
            st.write(f"**Garden Leave:** {c.get('garden_leave','')}")
            st.write(f"**Comm. Status:** {c.get('communication_status','')}")
            st.write(f"**L1 Manager:** {c.get('l1_manager','')} ({c.get('l1_manager_email','')})")
            st.write(f"**HRBP:** {c.get('hrbp_name','')} ({c.get('hrbp_mail_id','')})")
        st.write(f"**Remarks:** {c.get('remarks','') or '—'}")
        if c.get("approval_file_url"):
            st.link_button("View Approval Document", c["approval_file_url"])

    with calc_tab:
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Monthly Fixed Gross", _inr(c.get("monthly_fixed_gross")))
        cc2.metric("Severance Days",      c.get("severance_days", 0))
        cc3.metric("Severance Pay",       _inr(c.get("severance_pay_amount")))
        cc1.metric("Notice Period Days",  c.get("notice_period_days", 0))
        cc2.metric("Notice Period Amt",   _inr(c.get("notice_period_amount")))
        cc3.metric("Variable Pay",        _inr(c.get("variable_pay_amount")))
        st.caption(
            f"Tenure: {c.get('tenure','')}  |  "
            f"Tenure Cohort: {c.get('tenure_cohort','')}  |  "
            f"CTC Cohort: {c.get('ctc_cohort','')}  |  "
            f"Severance: {c.get('severance_applicability','')}  |  "
            f"Rehire: {c.get('rehire_status','')}"
        )

    with audit_tab:
        logs = get_audit_log(case_id)
        if logs:
            for lg in logs:
                note = f" — {lg['remarks']}" if lg.get("remarks") else ""
                st.write(f"`{str(lg.get('created_at',''))[:19]}` — **{lg['action']}** by {lg['user_email']}{note}")
        else:
            st.info("No audit entries yet.")

    # ── Admin actions ──────────────────────────────────────────────────────────
    st.divider()
    is_closed = str(c.get("closure_status", "")).lower() == "closed"
    email_sent = str(c.get("email_sent", "")).lower() == "sent"

    if is_closed:
        st.success("This case is **Closed**.")
        if not email_sent:
            if st.button("Send Closure Email to Employee", type="primary"):
                try:
                    from lib.email_utils import send_closure_email
                    send_closure_email(c)
                    update_case(case_id, {
                        "email_sent":        "Sent",
                        "email_sent_at":     _now(),
                        "email_sent_status": "Sent",
                    })
                    log_audit("CLOSURE_EMAIL_SENT", case_id, admin_email)
                    st.success("Closure email sent to employee!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Email failed: {e}")
        else:
            st.info(f"Closure email already sent at {str(c.get('email_sent_at',''))[:19]}")
            if st.button("Resend Closure Email"):
                try:
                    from lib.email_utils import send_closure_email
                    send_closure_email(c)
                    log_audit("CLOSURE_EMAIL_RESENT", case_id, admin_email)
                    st.success("Closure email resent!")
                except Exception as e:
                    st.error(f"Email failed: {e}")
        return

    st.subheader("Take Action")
    a1, a2 = st.columns([1, 2])
    with a1:
        action = st.selectbox("Action", [""] + ADMIN_ACTIONS, key=f"action_{case_id}")
    with a2:
        admin_remarks = st.text_area("Admin Remarks", height=80, key=f"remarks_{case_id}")

    if st.button("Apply Action", type="primary", disabled=not action):
        updates = {
            "admin_action":    action,
            "admin_remarks":   admin_remarks,
        }
        if action == "Closed":
            updates.update({
                "status":              "Admin Closed",
                "closure_status":      "Closed",
                "admin_action_status": "Closed",
                "admin_closed_status": "Closed",
                "admin_closed_at":     _now(),
                "admin_closed_by":     admin_email,
            })
            label = "CASE_CLOSED"
        elif action == "Sent Back":
            updates.update({
                "status":         "Sent Back",
                "sent_back_at":   _now(),
                "sent_back_by":   admin_email,
            })
            label = "CASE_SENT_BACK"

        update_case(case_id, updates)
        log_audit(label, case_id, admin_email, admin_remarks)

        try:
            from lib.email_utils import send_status_update
            send_status_update(get_case(case_id), action, admin_remarks)
        except Exception:
            pass

        st.success(f"Case marked as **{action}**.")
        st.rerun()


# ── All Cases tab ──────────────────────────────────────────────────────────────

def _all_cases_tab(admin_email: str):
    STATUS_ICON = {
        "Pending": "🟡", "Hold": "🟠", "Submitted": "🔵",
        "Sent Back": "🔴", "Admin Closed": "🟢",
    }

    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("Search by name, case ID, emp code…", placeholder="Search…")
    with col2:
        st.write("")
        st.write("")
        st.button("Refresh", use_container_width=True, key="refresh_cases")

    cases = get_all_cases()
    if search:
        q = search.lower()
        cases = [c for c in cases if q in (
            str(c.get("emp_name","")) + str(c.get("case_id","")) + str(c.get("emp_code",""))
        ).lower()]

    st.caption(f"{len(cases)} case(s)")

    if not cases:
        st.info("No cases yet. Managers need to initiate cases after Darwinbox sync.")
        return

    for case in cases:
        icon  = STATUS_ICON.get(case.get("status", ""), "⚪")
        label = (
            f"{icon} **{case['case_id']}** — {case.get('emp_name','')} "
            f"&nbsp;|&nbsp; LWD: {case.get('last_working_date','')} "
            f"&nbsp;|&nbsp; {case.get('entity','')}"
        )
        with st.expander(label):
            rc1, rc2, rc3, rc4 = st.columns([2, 2, 2, 1])
            rc1.write(f"**Reason:** {case.get('separation_reason','')}")
            rc2.write(f"**Comm.:** {case.get('communication_status','')}")
            rc3.write(f"**By:** {case.get('created_by','')}")
            if rc4.button("Open", key=f"admin_open_{case['case_id']}"):
                _show_case_detail(case["case_id"], admin_email)


# ── Sync tab ───────────────────────────────────────────────────────────────────

def _sync_tab(admin_email: str):
    st.subheader("Sync Employee Data")
    emp_count = get_employee_count()

    if emp_count == 0:
        st.error("**No employees in database yet.** Sync first before managers can see their teams.")
    else:
        st.info(f"**{emp_count}** employees currently in database.")

    # ── Option 1: Google Sheet (recommended) ──────────────────────────────────
    st.markdown("### Option 1 — Google Sheet (Recommended)")
    st.caption(
        "Reads from the hr-dashboard **Consolidated_Base** sheet which already has "
        "employee + CTC data merged and refreshes daily at 7 AM. No API calls needed."
    )

    sheet_url = os.getenv("GOOGLE_SHEET_CSV_URL", "")
    if not sheet_url:
        st.warning(
            "**GOOGLE_SHEET_CSV_URL not set.** To use this option:\n\n"
            "1. Open your hr-dashboard Google Sheet\n"
            "2. File → Share → **Publish to web**\n"
            "3. Sheet: **Consolidated_Base** → Format: **CSV** → Publish\n"
            "4. Copy the URL → add to Streamlit Secrets as `GOOGLE_SHEET_CSV_URL = \"...\"`"
        )
    else:
        gc1, gc2 = st.columns(2)
        with gc1:
            if st.button("Test Sheet Connection", use_container_width=True):
                with st.spinner("Checking sheet…"):
                    from lib.sheets import get_sheet_info
                    info = get_sheet_info()
                for k, v in info.items():
                    st.write(f"**{k}:** `{v}`")
        with gc2:
            if st.button("Sync from Google Sheet", type="primary", use_container_width=True):
                with st.spinner("Reading Consolidated_Base sheet…"):
                    try:
                        from lib.sheets import fetch_from_sheet
                        from lib.db import upsert_employees
                        employees = fetch_from_sheet()
                        count     = upsert_employees(employees)
                        log_audit("SHEET_SYNC", "SYSTEM", admin_email, f"Synced {count} employees from Google Sheet")
                        st.success(f"Sync complete — **{count}** employees upserted from Google Sheet.")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Sheet sync failed: {e}")

    st.divider()

    # ── Option 2: Darwinbox API directly ──────────────────────────────────────
    st.markdown("### Option 2 — Darwinbox API (Fallback)")
    st.caption("Hits Darwinbox master API directly. CTC data may be incomplete as it needs a separate payroll API call.")

    dc1, dc2 = st.columns(2)
    with dc1:
        if st.button("Test Darwinbox API", use_container_width=True):
            with st.spinner("Pinging Darwinbox…"):
                from lib.darwinbox import test_connection
                info = test_connection()
            for k, v in info.items():
                st.write(f"**{k}:** `{v}`")
    with dc2:
        if st.button("Sync from Darwinbox", use_container_width=True):
            with st.spinner("Fetching from Darwinbox API… (1-2 mins)"):
                try:
                    from lib.darwinbox import fetch_employee_master
                    from lib.db import upsert_employees
                    employees = fetch_employee_master()
                    count     = upsert_employees(employees)
                    log_audit("DARWINBOX_SYNC", "SYSTEM", admin_email, f"Synced {count} employees from API")
                    st.success(f"Sync complete — **{count}** employees upserted.")
                    st.balloons()
                except Exception as e:
                    st.error(f"Sync failed: {e}")


# ── Manage Users tab ───────────────────────────────────────────────────────────

def _users_tab(admin_email: str):
    st.subheader("User Roles — ADMIN & PAYROLL")
    st.caption("Managers are **auto-detected** from Darwinbox data. No manual setup needed for managers.")

    roles = get_all_user_roles()
    if roles:
        for r in roles:
            cols = st.columns([3, 2, 1, 1])
            cols[0].write(r["email"])
            cols[1].write(r["role"])
            cols[2].write("✅ Active" if r["active"] else "❌ Inactive")
            if r["email"] != admin_email and r.get("active"):
                if cols[3].button("Remove", key=f"rem_{r['id']}"):
                    deactivate_user_role(r["id"])
                    st.rerun()
    else:
        st.info("No explicit roles configured.")

    st.divider()
    st.subheader("Add ADMIN or PAYROLL User")
    with st.form("add_user"):
        new_email = st.text_input("Email (@cars24.com)")
        new_role  = st.selectbox("Role", ["ADMIN", "PAYROLL"])
        if st.form_submit_button("Add User", type="primary"):
            email = new_email.strip().lower()
            if not email.endswith("@cars24.com"):
                st.error("Only @cars24.com emails allowed.")
            else:
                upsert_user_role(email, new_role)
                log_audit("USER_ROLE_ADDED", "SYSTEM", admin_email, f"{email} → {new_role}")
                st.success(f"Added {email} as {new_role}.")
                st.rerun()


# ── Admin dashboard (includes My Team + My Cases) ──────────────────────────────

def admin_dashboard(user_email: str):
    st.subheader("Admin Dashboard")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "My Team", "My Cases", "All Cases", "Sync Darwinbox", "Manage Users"
    ])

    with tab1:
        st.caption("Your direct reports (based on Darwinbox data). Initiate separation cases here.")
        render_my_team(user_email)

    with tab2:
        st.caption("Separation cases you initiated as a manager.")
        render_my_cases(user_email)

    with tab3:
        _all_cases_tab(user_email)

    with tab4:
        _sync_tab(user_email)

    with tab5:
        _users_tab(user_email)
