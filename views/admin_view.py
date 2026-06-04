import os
import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from lib.db import (
    get_all_cases, get_case, update_case, log_audit,
    get_all_user_roles, upsert_user_role, deactivate_user_role,
    get_audit_log, ADMIN_ACTIONS,
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
        st.success("This case is **Admin Closed**.")

        email_col, reopen_col = st.columns(2)

        # ── Send / resend closure email ────────────────────────────────────────
        with email_col:
            if not email_sent:
                if st.button("Send Closure Email to Employee", type="primary", use_container_width=True):
                    try:
                        from lib.email_utils import send_closure_email
                        send_closure_email(c)
                        update_case(case_id, {
                            "email_sent":        "Sent",
                            "email_sent_at":     _now(),
                            "email_sent_status": "Sent",
                        })
                        log_audit("CLOSURE_EMAIL_SENT", case_id, admin_email)
                        st.success("Closure email sent!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Email failed: {e}")
            else:
                st.info(f"Email sent at {str(c.get('email_sent_at',''))[:19]}")
                if st.button("Resend Closure Email", use_container_width=True):
                    try:
                        from lib.email_utils import send_closure_email
                        send_closure_email(c)
                        log_audit("CLOSURE_EMAIL_RESENT", case_id, admin_email)
                        st.success("Closure email resent!")
                    except Exception as e:
                        st.error(f"Email failed: {e}")

        # ── Reopen case ────────────────────────────────────────────────────────
        with reopen_col:
            st.warning("Need to undo the closure?")
            reopen_remarks = st.text_input("Reason for reopening", key=f"reopen_{case_id}",
                                           placeholder="e.g. Closed by mistake")
            if st.button("Reopen Case", use_container_width=True):
                update_case(case_id, {
                    "status":              "Submitted",
                    "closure_status":      "",
                    "admin_action":        "",
                    "admin_action_status": "",
                    "admin_closed_status": "",
                    "admin_closed_at":     None,
                    "admin_closed_by":     "",
                    "admin_remarks":       f"[Reopened by {admin_email}] {reopen_remarks}",
                    "email_sent":          False,
                    "email_sent_at":       None,
                    "email_sent_status":   "",
                })
                log_audit("CASE_REOPENED", case_id, admin_email, reopen_remarks)
                st.success(f"Case **{case_id}** reopened — status reset to Submitted.")
                st.rerun()
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
                "status":               "Sent Back",
                "communication_status": "Pending",
                "sent_back_at":         _now(),
                "sent_back_by":         admin_email,
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
    st.subheader("Employee Data — Darwinbox API")

    st.success(
        "Employee data loads **automatically** from Darwinbox APIs "
        "(master + payroll CTC). Cached for **1 hour** — no manual sync needed."
    )
    st.info(
        "**What's included:** Active employees + anyone who left after 31 March 2026.\n\n"
        "**CTC data:** Fetched from the payroll API in batches — includes "
        "Fixed, Variable, PF, Gratuity, Medical for accurate severance calculations."
    )

    from lib.sheets import get_employee_count
    from lib.darwinbox import test_connection, fetch_employee_master
    from lib.db import upsert_employees

    count = get_employee_count()
    if count > 0:
        st.metric("Employees in database", count)
        st.caption("Managers read from DB instantly — no API call on every login.")
    else:
        st.warning("No employees in database yet. Click **Sync from Darwinbox** below.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Test Darwinbox API", use_container_width=True):
            with st.spinner("Pinging Darwinbox…"):
                info = test_connection()
            for k, v in info.items():
                st.write(f"**{k}:** `{v}`")

    with col2:
        if st.button("Sync from Darwinbox", type="primary", use_container_width=True):
            st.info("Fetching master + CTC data from Darwinbox. **Takes 1-2 minutes.** Do this once — managers will be instant after.")
            with st.spinner("Step 1/2 — Fetching from Darwinbox API…"):
                try:
                    employees = fetch_employee_master()
                except Exception as e:
                    st.error(f"Darwinbox fetch failed: {e}")
                    st.stop()
            with st.spinner(f"Step 2/2 — Saving {len(employees)} employees to database…"):
                try:
                    count = upsert_employees(employees)
                    log_audit("EMPLOYEE_SYNC", "SYSTEM", admin_email, f"Synced {count} employees")
                    st.success(f"Done — **{count}** employees saved. All managers can now log in instantly.")
                    st.balloons()
                except Exception as e:
                    st.error(f"Database write failed: {e}")


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
        st.caption("Your direct reports from Google Sheet (refreshes every 1 hour).")
        render_my_team(user_email)

    with tab2:
        st.caption("Separation cases you initiated.")
        try:
            render_my_cases(user_email)
        except Exception as e:
            st.error(f"Error loading cases: {e}")

    with tab3:
        _all_cases_tab(user_email)

    with tab4:
        _sync_tab(user_email)

    with tab5:
        _users_tab(user_email)
