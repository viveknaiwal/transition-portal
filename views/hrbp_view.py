import streamlit as st
from lib.db import get_all_cases, get_audit_log
from views.manager_view import _inject_css


def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


STATUS_ICON = {
    "Pending":      "🟡",
    "Hold":         "🟠",
    "Submitted":    "🔵",
    "Sent Back":    "🔴",
    "Admin Closed": "🟢",
}


def _case_detail(c: dict):
    """Read-only case detail — no action buttons."""
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Emp Code:** {c.get('emp_code','')}")
        st.write(f"**Entity / BU:** {c.get('entity','')} / {c.get('business_unit','')}")
        st.write(f"**Grade / Band:** {c.get('grade','')} / {c.get('band','')}")
        st.write(f"**Designation:** {c.get('external_designation','')}")
        st.write(f"**DOJ:** {c.get('doj','')}  |  **Group DOJ:** {c.get('group_doj','')}")
        st.write(f"**Date of Resignation:** {c.get('date_of_resignation','')}")
        st.write(f"**Last Working Date:** {c.get('last_working_date','')}")
        st.write(f"**L1 Manager:** {c.get('l1_manager','')} ({c.get('l1_manager_email','')})")
    with col2:
        st.write(f"**Separation Reason:** {c.get('separation_reason','')}")
        st.write(f"**Sub Reason:** {c.get('separation_sub_reason','')}")
        st.write(f"**Notice Type:** {c.get('immediate_exit_or_serving_notice','')}")
        st.write(f"**Garden Leave:** {c.get('garden_leave','')}")
        st.write(f"**Communication Status:** {c.get('communication_status','')}")
        st.write(f"**Remarks:** {c.get('remarks','') or '—'}")
        st.write(f"**Initiated By:** {c.get('created_by','')}")
        if c.get("admin_remarks"):
            st.write(f"**Admin Remarks:** {c.get('admin_remarks','')}")

    if c.get("approval_file_url"):
        st.link_button("📎 View Approval Document", c["approval_file_url"])

    st.caption("FNF Summary")
    tiles = [
        ("Monthly Fixed Gross",  _inr(c.get("monthly_fixed_gross"))),
        ("Severance Pay",        _inr(c.get("severance_pay_amount"))),
        ("Severance Days",       str(c.get("severance_days", 0))),
        ("Notice Period Amt",    _inr(c.get("notice_period_amount"))),
        ("Notice Period Days",   str(c.get("notice_period_days", 0))),
        ("Variable Pay",         _inr(c.get("variable_pay_amount"))),
    ]
    tile_html = "".join(
        f'<div style="background:#F9FAFB;border:1px solid #E5E7EB;border-radius:8px;'
        f'padding:12px 14px;min-width:0;">'
        f'<div style="font-size:11px;font-weight:700;color:#6B7280;text-transform:uppercase;'
        f'letter-spacing:.4px;margin-bottom:6px;">{lbl}</div>'
        f'<div style="font-size:16px;font-weight:800;color:#111827;'
        f'word-break:break-word;overflow-wrap:anywhere;line-height:1.3;">{val}</div>'
        f'</div>'
        for lbl, val in tiles
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px;">'
        f'{tile_html}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Tenure: {c.get('tenure','')}  ·  "
        f"Cohort: {c.get('tenure_cohort','')}  ·  "
        f"CTC Cohort: {c.get('ctc_cohort','')}  ·  "
        f"Rehire: {c.get('rehire_status','')}  ·  "
        f"Severance: {c.get('severance_applicability','')}"
    )

    with st.expander("Audit Trail"):
        logs = get_audit_log(c["case_id"])
        if logs:
            for lg in logs:
                note = f" — {lg['remarks']}" if lg.get("remarks") else ""
                st.write(f"`{str(lg.get('created_at',''))[:19]}` **{lg['action']}** by {lg['user_email']}{note}")
        else:
            st.caption("No audit entries yet.")


def hrbp_dashboard(user_email: str):
    _inject_css()

    st.subheader("HRBP — Case View")
    st.caption("Read-only view of separation cases assigned to your employees.")

    all_cases = get_all_cases()

    # Filter to cases where this HRBP is assigned
    my_cases = [c for c in all_cases if (c.get("hrbp_mail_id") or "").lower() == user_email.lower()]

    if not my_cases:
        st.info("No separation cases found for your employees yet.")
        return

    # ── Filters ────────────────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("Search by name, case ID, emp code…", placeholder="Search…")
    with col2:
        status_filter = st.selectbox("Filter by Status", ["All", "Pending", "Hold", "Submitted", "Sent Back", "Admin Closed"])

    if search:
        q = search.lower()
        my_cases = [c for c in my_cases if q in (
            str(c.get("emp_name","")) + str(c.get("case_id","")) + str(c.get("emp_code",""))
        ).lower()]

    if status_filter != "All":
        my_cases = [c for c in my_cases if c.get("status","") == status_filter]

    st.caption(f"{len(my_cases)} case(s)")

    for case in my_cases:
        icon  = STATUS_ICON.get(case.get("status",""), "⚪")
        label = (
            f"{icon} **{case['case_id']}** — {case.get('emp_name','')} "
            f"&nbsp;|&nbsp; LWD: {case.get('last_working_date','')} "
            f"&nbsp;|&nbsp; Status: {case.get('status','')}"
        )
        with st.expander(label):
            _case_detail(case)
