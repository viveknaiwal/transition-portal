import streamlit as st
from datetime import date
from lib.sheets import get_employees_for_manager   # live from Google Sheet (1-hr cache)
from lib.db import (
    get_cases_for_manager, create_case, update_case,
    log_audit, get_client,
    SEPARATION_REASONS, SUB_REASONS, COMMUNICATION_STATUSES,
)
from lib.calculations import calculate_case


def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


def _section(title: str, color: str = "blue"):
    """Colored section header — blue/purple/amber/green."""
    palette = {
        "blue":   ("#EFF6FF", "#1D4ED8", "#3B82F6"),
        "purple": ("#F5F3FF", "#5B21B6", "#7C3AED"),
        "amber":  ("#FFFBEB", "#92400E", "#F59E0B"),
        "green":  ("#F0FDF4", "#14532D", "#22C55E"),
    }
    bg, text, border = palette.get(color, ("#F9FAFB", "#374151", "#9CA3AF"))
    st.markdown(
        f'<div style="background:{bg};border-left:4px solid {border};padding:10px 14px;'
        f'border-radius:6px;margin:18px 0 10px 0;">'
        f'<span style="color:{text};font-weight:800;font-size:14px;letter-spacing:.3px;">{title}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _chip(status: str) -> str:
    STYLES = {
        "Pending":       ("FEF3C7", "92400E"),
        "Hold":          ("FEE2E2", "991B1B"),
        "Submitted":     ("DBEAFE", "1D4ED8"),
        "Sent Back":     ("FCE7F3", "9D174D"),
        "Admin Closed":  ("D1FAE5", "065F46"),
        "FNF Processed": ("D1FAE5", "065F46"),
        "Closed":        ("D1FAE5", "065F46"),
    }
    bg, fg = STYLES.get(status, ("F3F4F6", "6B7280"))
    return (f'<span style="background:#{bg};color:#{fg};padding:3px 10px;'
            f'border-radius:999px;font-size:11px;font-weight:700;">{status}</span>')


def _get_status(comm_status: str, old_status: str = "") -> str:
    if comm_status == "Completed":
        return "Submitted"
    if old_status.lower() in ("sent back", "sentback"):
        return "Sent Back"
    return "Pending" if comm_status in ("", "Pending") else "Hold"


def _upload_file(file, case_id: str) -> tuple[str, str]:
    sb   = get_client()
    path = f"cases/{case_id}/{file.name}"
    sb.storage.from_("attachments").upload(path, file.getvalue(), {"content-type": file.type or "application/pdf"})
    url = sb.storage.from_("attachments").get_public_url(path)
    return url, file.name


def _calc_cards(items: list[tuple]):
    """Render calculation results as a clean green card grid."""
    cards = ""
    for label, value in items:
        cards += (
            f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;'
            f'padding:10px 12px;text-align:center;">'
            f'<div style="font-size:10px;color:#166534;font-weight:800;'
            f'text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:15px;font-weight:800;color:#14532D;">{value}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));'
        f'gap:8px;margin:8px 0 4px 0;">{cards}</div>',
        unsafe_allow_html=True,
    )


def _amount_cards(items: list[tuple]):
    """Larger cards for monetary amounts."""
    cards = ""
    for label, value in items:
        cards += (
            f'<div style="background:#DCFCE7;border:1px solid #86EFAC;border-radius:8px;'
            f'padding:12px 14px;text-align:center;">'
            f'<div style="font-size:10px;color:#14532D;font-weight:800;'
            f'text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">{label}</div>'
            f'<div style="font-size:18px;font-weight:800;color:#15803D;">{value}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));'
        f'gap:8px;margin:4px 0 8px 0;">{cards}</div>',
        unsafe_allow_html=True,
    )


def _save_case(emp, user_email, is_edit, edit_case, calc, inputs):
    """Build case_data dict and write to Supabase."""
    sep_reason   = inputs["sep_reason"]
    sub_reason   = inputs["sub_reason"]
    dor          = inputs["dor"]
    lwd          = inputs["lwd"]
    notice_type  = inputs["notice_type"]
    garden_leave = inputs["garden_leave"]
    comm_status  = inputs["comm_status"]
    remarks      = inputs["remarks"]
    approval_file= inputs.get("approval_file")

    old_status = edit_case.get("status", "") if is_edit else ""
    new_status = _get_status(comm_status, old_status)

    emp_fields = [
        "emp_code", "entity", "business_unit", "lob", "function",
        "sub_function", "region", "site_name", "grade", "band",
        "external_designation", "internal_designation", "l1_manager",
        "l1_manager_email", "l2_manager", "l2_manager_email", "hrbp_name",
        "hrbp_mail_id", "doj", "group_doj", "employee_status", "gender",
        "fixed_ctc", "variable", "pli", "retention", "total_ctc",
        "monthly_gross", "provident_fund", "gratuity", "medical_insurance",
    ]
    case_data = {
        **{k: emp.get(k) for k in emp_fields},
        "emp_name":                         emp.get("full_name", ""),
        "official_email":                   emp.get("company_email_id", ""),
        "personal_email":                   emp.get("personal_email_id", ""),
        "personal_contact":                 emp.get("personal_mobile_no", ""),
        "date_of_resignation":              str(dor),
        "last_working_date":                str(lwd),
        "separation_reason":                sep_reason,
        "separation_sub_reason":            sub_reason,
        "immediate_exit_or_serving_notice": notice_type,
        "garden_leave":                     garden_leave,
        "communication_status":             comm_status,
        "remarks":                          remarks,
        "status":                           new_status,
        "created_by":                       user_email,
        "created_by_role":                  "MANAGER",
        **calc,
    }

    if is_edit:
        preserve = [
            "admin_remarks", "admin_action", "admin_action_status",
            "admin_closed_status", "admin_closed_at", "admin_closed_by",
            "closure_status", "payroll_downloaded_at",
            "email_sent", "email_sent_at", "email_sent_status",
            "created_at", "created_by", "created_by_role",
        ]
        for f in preserve:
            if f in edit_case:
                case_data[f] = edit_case[f]
        if old_status.lower() in ("sent back", "sentback"):
            for f in ("admin_action", "sent_back_at", "sent_back_by"):
                case_data[f] = ""

    if is_edit:
        case_id = edit_case["case_id"]
        update_case(case_id, case_data)
        if approval_file:
            try:
                url, fname = _upload_file(approval_file, case_id)
                update_case(case_id, {"approval_file_url": url, "approval_file_name": fname})
            except Exception:
                pass
        elif not remarks:
            update_case(case_id, {"approval_file_url": "", "approval_file_name": ""})
        log_audit("CASE_UPDATED", case_id, user_email)
        return case_id, False
    else:
        created = create_case(case_data)
        if not created:
            return None, False
        case_id = created["case_id"]
        if approval_file:
            try:
                url, fname = _upload_file(approval_file, case_id)
                update_case(case_id, {"approval_file_url": url, "approval_file_name": fname})
            except Exception:
                pass
        log_audit("CASE_CREATED", case_id, user_email)
        try:
            from lib.email_utils import send_case_created
            send_case_created({**case_data, "case_id": case_id})
        except Exception:
            pass
        return case_id, True


# ── Case form dialog (create + edit) — 2-phase: inputs → preview → confirm ────

@st.dialog("Separation Case", width="large")
def _show_case_form(emp: dict, user_email: str, edit_case: dict = None):
    from lib.calculations import _parse_date as _pd
    from datetime import date as _dt
    is_edit  = edit_case is not None
    emp_code = emp.get("emp_code", "")

    # Reset all form state when a different employee is opened
    if st.session_state.get("_cf_emp") != emp_code:
        for k in [k for k in st.session_state if k.startswith("cf_")]:
            del st.session_state[k]
        st.session_state["_cf_emp"]   = emp_code
        st.session_state["cf_phase"]  = "input"

    phase = st.session_state.get("cf_phase", "input")

    # Employee banner
    st.markdown(
        f"**{emp.get('full_name','')}** &nbsp;|&nbsp; "
        f"{emp.get('grade','')} / {emp.get('band','')} &nbsp;|&nbsp; "
        f"{emp.get('external_designation','')} &nbsp;|&nbsp; {emp.get('entity','')}",
        unsafe_allow_html=True,
    )
    st.divider()

    # ══ PHASE 1: INPUT FORM ════════════════════════════════════════════════════
    if phase == "input":
        _section("Case Inputs", "amber")

        # Everything in one st.form — no reruns during input = dates stay closed
        with st.form("case_inputs_form"):
            c1, c2 = st.columns(2)
            with c1:
                dor = st.date_input(
                    "Date of Resignation *",
                    value=_pd(edit_case.get("date_of_resignation")) if is_edit else st.session_state.get("cf_s_dor"),
                )
                lwd = st.date_input(
                    "Last Working Date *",
                    value=_pd(edit_case.get("last_working_date")) if is_edit else st.session_state.get("cf_s_lwd"),
                    min_value=_dt.today(),
                    help="Past dates are greyed out — LWD must be today or later.",
                )
                reason_opts = [""] + SEPARATION_REASONS
                prev_reason = edit_case.get("separation_reason", "") if is_edit else st.session_state.get("cf_s_reason", "")
                sep_reason  = st.selectbox("Separation Reason *", reason_opts,
                                            index=reason_opts.index(prev_reason) if prev_reason in reason_opts else 0)
                notice_opts = ["Serving Notice", "Immediate Exit"]
                prev_notice = edit_case.get("immediate_exit_or_serving_notice", notice_opts[0]) if is_edit else st.session_state.get("cf_s_notice", notice_opts[0])
                notice_type = st.selectbox("Notice Type *", notice_opts,
                                            index=notice_opts.index(prev_notice) if prev_notice in notice_opts else 0)

            with c2:
                # Flat sub-reason list (all 6 options — validated on submit)
                all_subs   = [""] + [s for opts in SUB_REASONS.values() for s in opts]
                prev_sub   = edit_case.get("separation_sub_reason", "") if is_edit else st.session_state.get("cf_s_sub", "")
                sub_reason = st.selectbox("Separation Sub Reason *", all_subs,
                                           index=all_subs.index(prev_sub) if prev_sub in all_subs else 0)
                garden_opts  = ["No", "Yes", "NA"]
                prev_garden  = edit_case.get("garden_leave", garden_opts[0]) if is_edit else st.session_state.get("cf_s_garden", garden_opts[0])
                garden_leave = st.selectbox("Garden Leave *", garden_opts,
                                             index=garden_opts.index(prev_garden) if prev_garden in garden_opts else 0)
                comm_opts   = [""] + COMMUNICATION_STATUSES
                prev_comm   = edit_case.get("communication_status", "") if is_edit else st.session_state.get("cf_s_comm", "")
                comm_status = st.selectbox("Communication Status *", comm_opts,
                                            index=comm_opts.index(prev_comm) if prev_comm in comm_opts else 0)

            prev_remarks = edit_case.get("remarks", "") if is_edit else st.session_state.get("cf_s_remarks", "")
            remarks      = st.text_area("Remarks / Exception", value=prev_remarks)

            existing_url  = edit_case.get("approval_file_url", "")  if is_edit else ""
            existing_name = edit_case.get("approval_file_name", "") if is_edit else ""
            if existing_url:
                st.markdown(f"📎 [Current Approval Doc: {existing_name or 'View'}]({existing_url})")
            approval_file = st.file_uploader(
                "Upload Approval PDF" + (" (replace existing)" if existing_url else ""),
                type=["pdf", "jpg", "jpeg", "png"],
            )
            if remarks and not approval_file and not existing_url:
                st.warning("Approval document is mandatory when remarks are entered.")

            preview_btn = st.form_submit_button(
                "Preview Calculations →", type="primary", use_container_width=True
            )

        if preview_btn:
            # Validate
            err = []
            if not sep_reason:  err.append("Separation Reason")
            if not sub_reason:  err.append("Separation Sub Reason")
            if not dor:         err.append("Date of Resignation")
            if not lwd:         err.append("Last Working Date")
            if not comm_status: err.append("Communication Status")
            if err:
                st.error(f"Missing required fields: {', '.join(err)}")
                return
            if sub_reason and sub_reason not in SUB_REASONS.get(sep_reason, []):
                st.error(f"'{sub_reason}' is not valid for '{sep_reason}'. Please select the correct sub-reason.")
                return
            if lwd < dor:
                st.error("Last Working Date cannot be before Date of Resignation.")
                return
            if lwd < _dt.today():
                st.error("Last Working Date cannot be a past date.")
                return
            if remarks and not approval_file and not existing_url:
                st.error("Approval document is required when remarks are entered.")
                return

            # Save inputs to session state → preview section appears below automatically
            st.session_state.update({
                "cf_s_reason":  sep_reason,  "cf_s_sub":     sub_reason,
                "cf_s_dor":     dor,         "cf_s_lwd":     lwd,
                "cf_s_notice":  notice_type, "cf_s_garden":  garden_leave,
                "cf_s_comm":    comm_status, "cf_s_remarks": remarks,
                "cf_s_file":    approval_file, "cf_s_ex_url": existing_url,
                "cf_phase":     "preview",
            })

    # ══ PHASE 2: CALCULATIONS PREVIEW + CONFIRM ════════════════════════════════
    elif phase == "preview":
        sep_reason   = st.session_state["cf_s_reason"]
        sub_reason   = st.session_state["cf_s_sub"]
        dor          = st.session_state["cf_s_dor"]
        lwd          = st.session_state["cf_s_lwd"]
        notice_type  = st.session_state["cf_s_notice"]
        garden_leave = st.session_state["cf_s_garden"]
        comm_status  = st.session_state["cf_s_comm"]
        remarks      = st.session_state["cf_s_remarks"]
        approval_file= st.session_state.get("cf_s_file")
        existing_url = st.session_state.get("cf_s_ex_url", "")

        # Input summary
        _section("Case Summary", "amber")
        s1, s2, s3 = st.columns(3)
        s1.write(f"**Date of Resignation:** {dor}")
        s2.write(f"**Last Working Date:** {lwd}")
        s3.write(f"**Notice Type:** {notice_type}")
        s1.write(f"**Separation Reason:** {sep_reason}")
        s2.write(f"**Sub Reason:** {sub_reason}")
        s3.write(f"**Garden Leave:** {garden_leave}")
        s1.write(f"**Comm Status:** {comm_status}")
        if remarks:
            st.write(f"**Remarks:** {remarks}")

        # Calculations
        calc = calculate_case(emp, {
            "last_working_date":               str(lwd),
            "date_of_resignation":             str(dor),
            "separation_reason":               sep_reason,
            "immediate_exit_or_serving_notice": notice_type,
        })
        _section("Calculations", "green")
        _calc_cards([
            ("Rehire Status",           calc["rehire_status"] or "—"),
            ("Tenure",                  calc["tenure"] or "—"),
            ("Tenure Cohort",           calc["tenure_cohort"] or "—"),
            ("Tenure Served",           str(calc["tenure_served"]) if calc["tenure_served"] != "" else "—"),
            ("CTC Cohort",              calc["ctc_cohort"] or "—"),
            ("Severance Applicability", calc["severance_applicability"] or "—"),
            ("Severance Days",          str(calc["severance_days"])),
            ("Notice Period (Days)",    str(calc["notice_period_days"])),
            ("Variable Days (prorata)", str(calc["variable_days_prorata"])),
        ])
        _amount_cards([
            ("Monthly Fixed Gross",  _inr(calc["monthly_fixed_gross"])),
            ("Severance Pay Amount", _inr(calc["severance_pay_amount"])),
            ("Notice Period Amount", _inr(calc["notice_period_amount"])),
            ("Variable Pay Amount",  _inr(calc["variable_pay_amount"])),
        ])

        st.divider()
        bc, cc = st.columns(2)
        if bc.button("← Edit", use_container_width=True):
            st.session_state["cf_phase"] = "input"

        if cc.button("✓ Confirm & Create Case", type="primary", use_container_width=True):
            inputs = {
                "sep_reason": sep_reason, "sub_reason":   sub_reason,
                "dor":        dor,        "lwd":          lwd,
                "notice_type":notice_type,"garden_leave": garden_leave,
                "comm_status":comm_status,"remarks":      remarks,
                "approval_file": approval_file,
            }
            with st.spinner("Saving case…"):
                case_id, is_new = _save_case(emp, user_email, is_edit, edit_case, calc, inputs)
            if case_id:
                action = "created" if is_new else "updated"
                st.success(f"Case **{case_id}** {action} successfully!")
                # Clear form state
                for k in [k for k in st.session_state if k.startswith("cf_")]:
                    del st.session_state[k]
                st.rerun()
            else:
                st.error("Failed to save case. Please try again.")


# ── Case detail dialog ─────────────────────────────────────────────────────────

@st.dialog("Case Details", width="large")
def _show_case_detail(case: dict):
    c = case
    st.markdown(f"### {c['case_id']} — {c.get('emp_name','')}")
    st.caption(
        f"Status: **{c.get('status','')}** &nbsp;|&nbsp; "
        f"Created: {str(c.get('created_at',''))[:10]}"
    )
    st.divider()

    t1, t2, t3 = st.tabs(["Employee Info", "Separation Details", "FNF Calculations"])

    with t1:
        cc1, cc2 = st.columns(2)
        with cc1:
            st.write(f"**Name:** {c.get('emp_name','')}")
            st.write(f"**Emp Code:** {c.get('emp_code','')}")
            st.write(f"**Entity / BU:** {c.get('entity','')} / {c.get('business_unit','')}")
            st.write(f"**Grade / Band:** {c.get('grade','')} / {c.get('band','')}")
            st.write(f"**Designation:** {c.get('external_designation','')}")
            st.write(f"**DOJ / Group DOJ:** {c.get('doj','')} / {c.get('group_doj','')}")
        with cc2:
            st.write(f"**L1 Manager:** {c.get('l1_manager','')} ({c.get('l1_manager_email','')})")
            st.write(f"**L2 Manager:** {c.get('l2_manager','')} ({c.get('l2_manager_email','')})")
            st.write(f"**HRBP:** {c.get('hrbp_name','')} ({c.get('hrbp_mail_id','')})")
            st.write(f"**Official Email:** {c.get('official_email','')}")
            st.write(f"**Personal Email:** {c.get('personal_email','')}")
            st.write(f"**Mobile:** {c.get('personal_contact','')}")

    with t2:
        cc1, cc2 = st.columns(2)
        with cc1:
            st.write(f"**Date of Resignation:** {c.get('date_of_resignation','')}")
            st.write(f"**Last Working Date:** {c.get('last_working_date','')}")
            st.write(f"**Separation Reason:** {c.get('separation_reason','')}")
            st.write(f"**Sub Reason:** {c.get('separation_sub_reason','')}")
        with cc2:
            st.write(f"**Notice Type:** {c.get('immediate_exit_or_serving_notice','')}")
            st.write(f"**Garden Leave:** {c.get('garden_leave','')}")
            st.write(f"**Comm. Status:** {c.get('communication_status','')}")
            st.write(f"**Remarks:** {c.get('remarks','')}")
        if c.get("approval_file_url"):
            st.link_button("View Approval Document", c["approval_file_url"])

    with t3:
        cc1, cc2 = st.columns(2)
        with cc1:
            st.metric("Monthly Fixed Gross", _inr(c.get("monthly_fixed_gross")))
            st.metric("Notice Period Days",  c.get("notice_period_days", 0))
            st.metric("Notice Period Amt",   _inr(c.get("notice_period_amount")))
        with cc2:
            st.metric("Severance Applicability", c.get("severance_applicability", "-"))
            st.metric("Severance Days",           c.get("severance_days", 0))
            st.metric("Severance Pay",            _inr(c.get("severance_pay_amount")))
        st.metric("Variable Pay", _inr(c.get("variable_pay_amount")))
        st.caption(
            f"Tenure: {c.get('tenure','')}  |  "
            f"Rehire: {c.get('rehire_status','')}  |  "
            f"CTC Cohort: {c.get('ctc_cohort','')}"
        )

    if c.get("admin_remarks"):
        st.info(f"**Admin Remarks:** {c['admin_remarks']}")


# ── Shared render functions (used by admin_view too) ──────────────────────────

def render_my_team(user_email: str):
    try:
        employees = get_employees_for_manager(user_email)
    except Exception as e:
        st.error(f"Could not load employee data: {e}")
        st.info("Ask your Admin to go to **Employee Data tab → Sync from Darwinbox**.")
        return

    if not employees:
        st.info(
            "No active direct reports found under your email. "
            "If this is wrong, the Google Sheet may not have your email as L1 Manager."
        )
        return

    st.caption(f"{len(employees)} active direct report(s) found.")
    header = st.columns([3, 2, 2, 2, 1.5])
    for h, t in zip(header, ["Name", "Designation", "Grade", "Entity", "Action"]):
        h.markdown(f"**{t}**")
    st.divider()

    for emp in employees:
        cols = st.columns([3, 2, 2, 2, 1.5])
        cols[0].write(f"**{emp['full_name']}**")
        cols[1].write(emp.get("external_designation", ""))
        cols[2].write(emp.get("grade", ""))
        cols[3].write(emp.get("entity", ""))
        if cols[4].button("Open", key=f"open_{user_email[:4]}_{emp['emp_code']}"):
            _show_case_form(emp, user_email)


def render_my_cases(user_email: str):
    cases = get_cases_for_manager(user_email)
    if not cases:
        st.info("No separation cases created by you yet.")
        return

    STATUS_ICON = {
        "Pending": "🟡", "Hold": "🟠", "Submitted": "🔵",
        "Sent Back": "🔴", "Admin Closed": "🟢",
    }

    for case in cases:
        icon  = STATUS_ICON.get(case.get("status", ""), "⚪")
        label = (
            f"{icon} **{case['case_id']}** — {case.get('emp_name','')} "
            f"— LWD: {case.get('last_working_date','')}"
        )
        with st.expander(label):
            cc1, cc2, cc3 = st.columns(3)
            cc1.markdown(_chip(case.get("status", "")), unsafe_allow_html=True)
            cc2.write(f"**Reason:** {case.get('separation_reason','')}")
            cc3.write(f"**Comm.:** {case.get('communication_status','')}")
            if case.get("admin_remarks"):
                st.warning(f"Admin remarks: {case['admin_remarks']}")

            btn_col1, btn_col2 = st.columns(2)
            if btn_col1.button("View Details", key=f"view_{case['case_id']}"):
                _show_case_detail(case)

            # Editable if not closed and status allows
            editable = (
                str(case.get("closure_status", "")).lower() != "closed"
                and case.get("status", "").lower() in ("pending", "hold", "sent back", "sentback")
            )
            if editable:
                # Reconstruct employee dict from case
                emp_from_case = {
                    "full_name":            case.get("emp_name", ""),
                    "emp_code":             case.get("emp_code", ""),
                    "company_email_id":     case.get("official_email", ""),
                    "personal_email_id":    case.get("personal_email", ""),
                    "personal_mobile_no":   case.get("personal_contact", ""),
                    "entity":               case.get("entity", ""),
                    "business_unit":        case.get("business_unit", ""),
                    "lob":                  case.get("lob", ""),
                    "function":             case.get("function", ""),
                    "sub_function":         case.get("sub_function", ""),
                    "region":               case.get("region", ""),
                    "site_name":            case.get("site_name", ""),
                    "grade":                case.get("grade", ""),
                    "band":                 case.get("band", ""),
                    "external_designation": case.get("external_designation", ""),
                    "internal_designation": case.get("internal_designation", ""),
                    "l1_manager":           case.get("l1_manager", ""),
                    "l1_manager_email":     case.get("l1_manager_email", ""),
                    "l2_manager":           case.get("l2_manager", ""),
                    "l2_manager_email":     case.get("l2_manager_email", ""),
                    "hrbp_name":            case.get("hrbp_name", ""),
                    "hrbp_mail_id":         case.get("hrbp_mail_id", ""),
                    "doj":                  case.get("doj", ""),
                    "group_doj":            case.get("group_doj", ""),
                    "employee_status":      case.get("employee_status", ""),
                    "gender":               case.get("gender", ""),
                    "fixed_ctc":            case.get("fixed_ctc", 0),
                    "variable":             case.get("variable", 0),
                    "pli":                  case.get("pli", 0),
                    "retention":            case.get("retention", 0),
                    "total_ctc":            case.get("total_ctc", 0),
                    "monthly_gross":        case.get("monthly_gross", 0),
                    "provident_fund":       case.get("provident_fund", 0),
                    "gratuity":             case.get("gratuity", 0),
                    "medical_insurance":    case.get("medical_insurance", 0),
                }
                if btn_col2.button("Edit", key=f"edit_{case['case_id']}"):
                    _show_case_form(emp_from_case, user_email, edit_case=case)


# ── Manager-only dashboard ─────────────────────────────────────────────────────

def manager_dashboard(user_email: str):
    st.subheader("My Dashboard")
    tab1, tab2 = st.tabs(["My Team", "My Cases"])
    with tab1:
        render_my_team(user_email)
    with tab2:
        render_my_cases(user_email)
