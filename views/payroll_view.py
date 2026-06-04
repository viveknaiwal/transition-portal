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
                    f"**{case['case_id']}** — {case.get('emp_name','')} — LWD: {case.get('last_working_date','')}"
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Severance Pay",     _inr(case.get("severance_pay_amount")))
                    c2.metric("Notice Period Amt", _inr(case.get("notice_period_amount")))
                    c3.metric("Variable Pay",      _inr(case.get("variable_pay_amount")))
                    st.write(
                        f"**Entity:** {case.get('entity','')} &nbsp;|&nbsp; "
                        f"**Grade:** {case.get('grade','')} &nbsp;|&nbsp; "
                        f"**Tenure:** {case.get('tenure','')} &nbsp;|&nbsp; "
                        f"**Rehire:** {case.get('rehire_status','')}"
                    )
                    if case.get("approval_file_url"):
                        st.link_button("View Approval Document", case["approval_file_url"])

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
            display = ["case_id", "emp_name", "entity", "grade", "last_working_date",
                       "separation_reason", "status", "closure_status",
                       "severance_pay_amount", "notice_period_amount", "variable_pay_amount"]
            rows = [{col: c.get(col, "") for col in display} for c in all_cases]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
