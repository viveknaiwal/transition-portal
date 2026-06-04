import streamlit as st
import pandas as pd
from io import StringIO
from lib.db import get_fnf_ready_cases, get_all_cases, update_case, log_audit


def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


FNF_CSV_COLUMNS = [
    "case_id", "emp_code", "emp_name", "official_email", "entity",
    "business_unit", "grade", "band", "external_designation",
    "l1_manager", "l1_manager_email", "hrbp_name", "hrbp_mail_id",
    "date_of_resignation", "last_working_date", "separation_reason",
    "immediate_exit_or_serving_notice", "garden_leave",
    "doj", "group_doj", "gender",
    "total_ctc", "fixed_ctc", "variable", "monthly_gross",
    "provident_fund", "gratuity", "medical_insurance",
    "monthly_fixed_gross", "tenure", "tenure_cohort", "tenure_served",
    "ctc_cohort", "rehire_status",
    "severance_applicability", "severance_days", "severance_pay_amount",
    "notice_period_days", "notice_period_amount",
    "variable_days_prorata", "variable_pay_amount",
    "april_fy_2025", "one_april_2025",
    "personal_email", "personal_contact",
    "remarks", "admin_remarks",
]


def _to_csv(cases: list) -> str:
    rows = []
    for c in cases:
        rows.append({col: c.get(col, "") for col in FNF_CSV_COLUMNS})
    df = pd.DataFrame(rows, columns=FNF_CSV_COLUMNS)
    buf = StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def payroll_dashboard(user_email: str):
    st.subheader("Payroll — Full & Final Settlement")

    tab1, tab2 = st.tabs(["FNF Ready", "All Cases (Read-Only)"])

    # ── Tab 1: FNF Ready ───────────────────────────────────────────────────────
    with tab1:
        cases = get_fnf_ready_cases()
        st.caption(f"{len(cases)} case(s) approved and ready for FNF processing")

        if not cases:
            st.info("No cases are currently in Approved status.")
        else:
            # Download button at top
            csv_data = _to_csv(cases)
            st.download_button(
                label="Download FNF Report (CSV)",
                data=csv_data,
                file_name="fnf_report.csv",
                mime="text/csv",
                type="primary",
            )
            st.divider()

            for case in cases:
                with st.expander(f"**{case['case_id']}** — {case.get('emp_name','')} — LWD: {case.get('last_working_date','')}"):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Severance Pay",      _inr(case.get("severance_pay_amount")))
                    c2.metric("Notice Period Amt",  _inr(case.get("notice_period_amount")))
                    c3.metric("Variable Pay",       _inr(case.get("variable_pay_amount")))

                    sc1, sc2 = st.columns([3, 1])
                    sc1.write(
                        f"**Entity:** {case.get('entity','')} &nbsp;|&nbsp; "
                        f"**Grade:** {case.get('grade','')} &nbsp;|&nbsp; "
                        f"**Tenure:** {case.get('tenure','')} &nbsp;|&nbsp; "
                        f"**Rehire:** {case.get('rehire_status','')}"
                    )
                    if sc2.button("Mark FNF Processed", key=f"fnf_{case['case_id']}"):
                        from datetime import datetime, timezone
                        update_case(case["case_id"], {
                            "status":                "FNF Processed",
                            "payroll_downloaded_at": datetime.now(timezone.utc).isoformat(),
                        })
                        log_audit("FNF_PROCESSED", case["case_id"], user_email)
                        st.success(f"Marked {case['case_id']} as FNF Processed")
                        st.rerun()

    # ── Tab 2: All cases read-only ─────────────────────────────────────────────
    with tab2:
        all_cases = get_all_cases()
        if not all_cases:
            st.info("No cases found.")
        else:
            csv_all = _to_csv(all_cases)
            st.download_button(
                label="Download All Cases (CSV)",
                data=csv_all,
                file_name="all_cases.csv",
                mime="text/csv",
            )
            display_cols = [
                "case_id", "emp_name", "entity", "grade", "last_working_date",
                "separation_reason", "status", "severance_pay_amount",
                "notice_period_amount", "variable_pay_amount",
            ]
            rows = [{col: c.get(col, "") for col in display_cols} for c in all_cases]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
