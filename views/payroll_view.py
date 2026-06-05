import streamlit as st
import pandas as pd
from io import StringIO
from datetime import datetime, timezone
from lib.db import get_fnf_ready_cases, get_all_cases, update_case, log_audit


def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


def _chip(status: str) -> str:
    STYLES = {
        "Pending":       ("FEF3C7", "92400E"),
        "Hold":          ("FEE2E2", "991B1B"),
        "Submitted":     ("DBEAFE", "1D4ED8"),
        "Sent Back":     ("FCE7F3", "9D174D"),
        "Admin Closed":  ("D1FAE5", "065F46"),
        "FNF Processed": ("D1FAE5", "065F46"),
    }
    bg, fg = STYLES.get(str(status), ("F3F4F6", "6B7280"))
    return f'<span style="background:#{bg};color:#{fg};padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;">{status}</span>'


# Exact payroll column order from spec §18
# (display_name, db_column)
PAYROLL_COLS = [
    ("Case ID",                          "case_id"),
    ("Emp Code",                         "emp_code"),
    ("Emp Name",                         "emp_name"),
    ("Official Email",                   "official_email"),
    ("Personal Email ID",                "personal_email"),
    ("Personal Contact Number",          "personal_contact"),
    ("Entity",                           "entity"),
    ("Business Unit",                    "business_unit"),
    ("LOB",                              "lob"),
    ("Function",                         "function"),
    ("Sub-Function",                     "sub_function"),
    ("Region",                           "region"),
    ("Site Name",                        "site_name"),
    ("Grade",                            "grade"),
    ("Band",                             "band"),
    ("External Designation",             "external_designation"),
    ("Internal Designation",             "internal_designation"),
    ("L1 Manager",                       "l1_manager"),
    ("L1 Manager Email",                 "l1_manager_email"),
    ("L2 Manager",                       "l2_manager"),
    ("L2 Manager Email",                 "l2_manager_email"),
    ("HRBP Name",                        "hrbp_name"),
    ("HRBP Mail ID",                     "hrbp_mail_id"),
    ("DOJ",                              "doj"),
    ("Group DOJ",                        "group_doj"),
    ("Date of Resignation",              "date_of_resignation"),
    ("Last Working Date",                "last_working_date"),
    ("Employee Status",                  "employee_status"),
    ("Rehire Status",                    "rehire_status"),
    ("Immediate Exit or Serving Notice", "immediate_exit_or_serving_notice"),
    ("Tenure",                           "tenure"),
    ("Tenure Served",                    "tenure_served"),
    ("Tenure Cohort",                    "tenure_cohort"),
    ("CTC Cohort",                       "ctc_cohort"),
    ("Fixed",                            "fixed_ctc"),
    ("Variable",                         "variable"),
    ("PLI",                              "pli"),
    ("Retention",                        "retention"),
    ("Fixed CTC",                        "fixed_ctc"),
    ("Total CTC",                        "total_ctc"),
    ("Monthly Gross",                    "monthly_gross"),
    ("Monthly Fixed Gross",              "monthly_fixed_gross"),
    ("Variable Pay Amount",              "variable_pay_amount"),
    ("Variable (Days) (prorata)",        "variable_days_prorata"),
    ("Variable Days",                    "variable_days_prorata"),
    ("Provident Fund",                   "provident_fund"),
    ("Gratuity",                         "gratuity"),
    ("Medical Insurance",                "medical_insurance"),
    ("Notice Period",                    "notice_period_amount"),
    ("Notice Period (Days)",             "notice_period_days"),
    ("Notice Period Amount",             "notice_period_amount"),
    ("Garden Leave",                     "garden_leave"),
    ("Severance Applicability",          "severance_applicability"),
    ("Severance Pay",                    "severance_pay_amount"),
    ("Severance Days",                   "severance_days"),
    ("Severance Pay Amount",             "severance_pay_amount"),
    ("Separation Reason",                "separation_reason"),
    ("Separation Sub Reason",            "separation_sub_reason"),
    ("Gender",                           "gender"),
    ("Payroll Downloaded At",            "payroll_downloaded_at"),
    ("Email Sent",                       "email_sent"),
    ("Email Sent At",                    "email_sent_at"),
    ("Email Sent Status",                "email_sent_status"),
    ("Email check",                      "email_check"),
    ("Communication Status",             "communication_status"),
    ("Status",                           "status"),
    ("Closure Status",                   "closure_status"),
    ("Admin Action",                     "admin_action"),
    ("Admin Action Status",              "admin_action_status"),
    ("Admin Closed Status",              "admin_closed_status"),
    ("Admin Closed At",                  "admin_closed_at"),
    ("Admin Closed By",                  "admin_closed_by"),
    ("Sent Back At",                     "sent_back_at"),
    ("Sent Back By",                     "sent_back_by"),
    ("Created At",                       "created_at"),
    ("Created By",                       "created_by"),
    ("Created By Role",                  "created_by_role"),
    ("Updated At",                       "updated_at"),
    ("Remarks / Exception",              "remarks"),
    ("Remarks - If Any",                 "remarks"),
    ("Admin Remarks",                    "admin_remarks"),
    ("Approval File URL",                "approval_file_url"),
    ("Approval File Name",               "approval_file_name"),
    ("April fy 2025",                    "april_fy_2025"),
    ("1 April 2025",                     "one_april_2025"),
]


def _to_csv(cases: list) -> bytes:
    rows = []
    for c in cases:
        row = {}
        for display_name, db_col in PAYROLL_COLS:
            row[display_name] = c.get(db_col, "") or ""
        rows.append(row)
    df  = pd.DataFrame(rows, columns=[col[0] for col in PAYROLL_COLS])
    buf = StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def payroll_dashboard(user_email: str):
    st.subheader("Payroll — Full & Final Settlement")

    tab1, tab2 = st.tabs(["FNF Ready (Closed Cases)", "All Cases"])

    # ── Tab 1: Closed cases ready for FNF ─────────────────────────────────────
    with tab1:
        cases = get_fnf_ready_cases()
        st.caption(f"{len(cases)} case(s) with Closure Status = Closed")

        if not cases:
            st.info("No closed cases yet.")
        else:
            col1, col2 = st.columns([1, 1])
            with col1:
                csv_bytes = _to_csv(cases)
                if st.download_button(
                    label="Download FNF Report (CSV)",
                    data=csv_bytes,
                    file_name="fnf_report.csv",
                    mime="text/csv",
                    type="primary",
                    use_container_width=True,
                ):
                    now = datetime.now(timezone.utc).isoformat()
                    for case in cases:
                        update_case(case["case_id"], {
                            "payroll_downloaded_at": now,
                            "status":               "FNF Processed",
                        })
                        log_audit("PAYROLL_DOWNLOADED", case["case_id"], user_email)
                    st.success(f"Downloaded {len(cases)} cases. Marked as FNF Processed.")
                    st.rerun()

            st.divider()
            for case in cases:
                with st.expander(
                    f"**{case['case_id']}** — {case.get('emp_name','')} "
                    f"| {case.get('entity','')} | {case.get('grade','')} "
                    f"| LWD: {case.get('last_working_date','')}"
                ):
                    # ── Employee info ──────────────────────────────────────────
                    i1, i2, i3 = st.columns(3)
                    i1.write(f"**Emp Code:** {case.get('emp_code','')}")
                    i1.write(f"**Official Email:** {case.get('official_email','')}")
                    i1.write(f"**Personal Email:** {case.get('personal_email','')}")
                    i1.write(f"**Contact:** {case.get('personal_contact','')}")
                    i2.write(f"**Entity / BU:** {case.get('entity','')} / {case.get('business_unit','')}")
                    i2.write(f"**Grade / Band:** {case.get('grade','')} / {case.get('band','')}")
                    i2.write(f"**Designation:** {case.get('external_designation','')}")
                    i2.write(f"**Gender:** {case.get('gender','')}")
                    i3.write(f"**DOJ:** {case.get('doj','')}  |  **Group DOJ:** {case.get('group_doj','')}")
                    i3.write(f"**DOR:** {case.get('date_of_resignation','')}  |  **LWD:** {case.get('last_working_date','')}")
                    i3.write(f"**Tenure:** {case.get('tenure','')}  |  **Served:** {case.get('tenure_served','')}")
                    i3.write(f"**Tenure Cohort:** {case.get('tenure_cohort','')}  |  **CTC Cohort:** {case.get('ctc_cohort','')}")

                    st.divider()

                    # ── FNF amounts + days ─────────────────────────────────────
                    st.caption("FNF Calculations")
                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("Monthly Fixed Gross",  _inr(case.get("monthly_fixed_gross")))
                    m2.metric("Severance Pay",         _inr(case.get("severance_pay_amount")))
                    m3.metric("Severance Days",        case.get("severance_days", 0))
                    m4.metric("Notice Period Amt",     _inr(case.get("notice_period_amount")))
                    m5.metric("Notice Period Days",    case.get("notice_period_days", 0))
                    m6.metric("Variable Pay",          _inr(case.get("variable_pay_amount")))

                    # ── CTC breakdown ──────────────────────────────────────────
                    st.caption("CTC Breakdown")
                    t1, t2, t3, t4, t5, t6 = st.columns(6)
                    t1.metric("Fixed CTC",       _inr(case.get("fixed_ctc")))
                    t2.metric("Variable",         _inr(case.get("variable")))
                    t3.metric("Total CTC",        _inr(case.get("total_ctc")))
                    t4.metric("Provident Fund",   _inr(case.get("provident_fund")))
                    t5.metric("Gratuity",         _inr(case.get("gratuity")))
                    t6.metric("Medical Insurance",_inr(case.get("medical_insurance")))

                    st.divider()

                    # ── Separation details ─────────────────────────────────────
                    s1, s2 = st.columns(2)
                    s1.write(f"**Reason:** {case.get('separation_reason','')} — {case.get('separation_sub_reason','')}")
                    s1.write(f"**Notice Type:** {case.get('immediate_exit_or_serving_notice','')}  |  **Garden Leave:** {case.get('garden_leave','')}")
                    s1.write(f"**Severance Applicability:** {case.get('severance_applicability','')}")
                    s1.write(f"**Rehire Status:** {case.get('rehire_status','')}")
                    s2.write(f"**HRBP:** {case.get('hrbp_name','')} ({case.get('hrbp_mail_id','')})")
                    s2.write(f"**L1 Manager:** {case.get('l1_manager','')} ({case.get('l1_manager_email','')})")
                    s2.write(f"**Closed By:** {case.get('admin_closed_by','')}  |  **At:** {str(case.get('admin_closed_at',''))[:10]}")
                    s2.write(f"**Email Sent:** {case.get('email_sent','')}  |  **At:** {str(case.get('email_sent_at',''))[:10]}")

                    if case.get("remarks"):
                        st.info(f"Remarks: {case['remarks']}")
                    if case.get("admin_remarks"):
                        st.warning(f"Admin Remarks: {case['admin_remarks']}")
                    if case.get("approval_file_url"):
                        st.link_button("📎 View Approval Document", case["approval_file_url"])

    # ── Tab 2: All cases read-only ─────────────────────────────────────────────
    with tab2:
        all_cases = get_all_cases()
        if not all_cases:
            st.info("No cases found.")
        else:
            st.download_button(
                label="Download All Cases (CSV)",
                data=_to_csv(all_cases),
                file_name="all_cases.csv",
                mime="text/csv",
            )
            display = [
                ("Case ID",              "case_id"),
                ("Emp Code",             "emp_code"),
                ("Emp Name",             "emp_name"),
                ("Entity",               "entity"),
                ("Grade",                "grade"),
                ("Designation",          "external_designation"),
                ("DOJ",                  "doj"),
                ("Group DOJ",            "group_doj"),
                ("DOR",                  "date_of_resignation"),
                ("LWD",                  "last_working_date"),
                ("Tenure",               "tenure"),
                ("Reason",               "separation_reason"),
                ("Notice Type",          "immediate_exit_or_serving_notice"),
                ("Garden Leave",         "garden_leave"),
                ("Severance Applicable", "severance_applicability"),
                ("Sev Days",             "severance_days"),
                ("Sev Pay",              "severance_pay_amount"),
                ("Notice Days",          "notice_period_days"),
                ("Notice Pay",           "notice_period_amount"),
                ("Variable Pay",         "variable_pay_amount"),
                ("Monthly Fixed Gross",  "monthly_fixed_gross"),
                ("Rehire",               "rehire_status"),
                ("Status",               "status"),
                ("Closure Status",       "closure_status"),
                ("Email Sent",           "email_sent"),
                ("HRBP",                 "hrbp_name"),
                ("L1 Manager",           "l1_manager"),
            ]
            rows = [{lbl: c.get(col, "") for lbl, col in display} for c in all_cases]
            st.dataframe(pd.DataFrame(rows, columns=[d[0] for d in display]),
                         use_container_width=True, hide_index=True)
