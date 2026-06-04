import streamlit as st
from datetime import date
from lib.sheets import get_employees_for_manager
from lib.db import (
    get_cases_for_manager, create_case, update_case,
    log_audit, get_client,
    SEPARATION_REASONS, SUB_REASONS, COMMUNICATION_STATUSES,
)
from lib.calculations import calculate_case, _parse_date as _pd


# ── Helpers ────────────────────────────────────────────────────────────────────

def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


def _section(title, color="blue"):
    palette = {
        "blue":   ("#EFF6FF", "#1D4ED8", "#3B82F6"),
        "purple": ("#F5F3FF", "#5B21B6", "#7C3AED"),
        "amber":  ("#FFFBEB", "#92400E", "#F59E0B"),
        "green":  ("#F0FDF4", "#14532D", "#22C55E"),
    }
    bg, text, border = palette.get(color, ("#F9FAFB", "#374151", "#9CA3AF"))
    st.markdown(
        f'<div style="background:{bg};border-left:4px solid {border};padding:10px 14px;'
        f'border-radius:6px;margin:16px 0 8px 0;">'
        f'<span style="color:{text};font-weight:800;font-size:14px;">{title}</span></div>',
        unsafe_allow_html=True,
    )


def _chip(status):
    S = {
        "Pending":       ("FEF3C7","92400E"), "Hold":         ("FEE2E2","991B1B"),
        "Submitted":     ("DBEAFE","1D4ED8"), "Sent Back":    ("FCE7F3","9D174D"),
        "Admin Closed":  ("D1FAE5","065F46"), "FNF Processed":("D1FAE5","065F46"),
    }
    bg, fg = S.get(str(status), ("F3F4F6","6B7280"))
    return f'<span style="background:#{bg};color:#{fg};padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;">{status}</span>'


def _calc_cards(items):
    cards = "".join(
        f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;border-radius:8px;'
        f'padding:10px 12px;text-align:center;">'
        f'<div style="font-size:10px;color:#166534;font-weight:800;'
        f'text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">{lbl}</div>'
        f'<div style="font-size:15px;font-weight:800;color:#14532D;">{val}</div></div>'
        for lbl, val in items
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));'
        f'gap:8px;margin:8px 0;">{cards}</div>', unsafe_allow_html=True,
    )


def _amount_cards(items):
    cards = "".join(
        f'<div style="background:#DCFCE7;border:1px solid #86EFAC;border-radius:8px;'
        f'padding:12px 14px;text-align:center;">'
        f'<div style="font-size:10px;color:#14532D;font-weight:800;'
        f'text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">{lbl}</div>'
        f'<div style="font-size:18px;font-weight:800;color:#15803D;">{val}</div></div>'
        for lbl, val in items
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));'
        f'gap:8px;margin:4px 0 8px 0;">{cards}</div>', unsafe_allow_html=True,
    )


def _upload_file(file, case_id):
    sb   = get_client()
    path = f"cases/{case_id}/{file.name}"
    sb.storage.from_("attachments").upload(path, file.getvalue(), {"content-type": file.type or "application/pdf"})
    return sb.storage.from_("attachments").get_public_url(path), file.name


# ── Inline case form — no dialog, no st.form, live calculations ───────────────

def _render_case_form(emp: dict, user_email: str, edit_case: dict = None):
    is_edit  = edit_case is not None
    emp_code = emp.get("emp_code", "")

    # One-time initialisation of form values for this employee
    init_key = f"_cf_init_{emp_code}_{'edit' if is_edit else 'new'}"
    if init_key not in st.session_state:
        st.session_state["cf_dor"]    = _pd(edit_case.get("date_of_resignation")) if is_edit else None
        st.session_state["cf_lwd"]    = _pd(edit_case.get("last_working_date"))   if is_edit else None
        st.session_state["cf_reason"] = edit_case.get("separation_reason","")     if is_edit else ""
        st.session_state["cf_sub"]    = edit_case.get("separation_sub_reason","") if is_edit else ""
        st.session_state["cf_notice"] = edit_case.get("immediate_exit_or_serving_notice","Serving Notice") if is_edit else "Serving Notice"
        st.session_state["cf_garden"] = edit_case.get("garden_leave","No")        if is_edit else "No"
        st.session_state["cf_comm"]   = edit_case.get("communication_status","")  if is_edit else ""
        st.session_state["cf_rem"]    = edit_case.get("remarks","")               if is_edit else ""
        st.session_state[init_key]    = True

    # ── Employee banner ───────────────────────────────────────────────────────
    _section("Employee Details", "blue")
    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.write(f"**{emp.get('full_name','')}**")
    bc2.write(f"Grade: {emp.get('grade','')} / {emp.get('band','')}")
    bc3.write(emp.get("external_designation",""))
    bc4.write(emp.get("entity",""))
    bc1.caption(f"DOJ: {emp.get('group_doj','') or emp.get('doj','')}")
    bc2.caption(f"HRBP: {emp.get('hrbp_name','')}")
    bc3.caption(f"L1: {emp.get('l1_manager','')}")
    bc4.caption(f"L2: {emp.get('l2_manager','')}")

    # ── Case inputs — regular widgets (no st.form) so calcs show live ────────
    _section("Case Inputs", "amber")
    c1, c2 = st.columns(2)

    with c1:
        dor = st.date_input("Date of Resignation *", key="cf_dor")
        lwd = st.date_input("Last Working Date *", key="cf_lwd",
                             min_value=date.today(),
                             help="Past dates are greyed out")

        # LWD inline validation
        if lwd and dor:
            if lwd < dor:
                st.error("LWD cannot be before Date of Resignation.")
        elif lwd and lwd < date.today():
            st.error("LWD cannot be a past date.")

        reason_opts = [""] + SEPARATION_REASONS
        sep_reason  = st.selectbox("Separation Reason *", reason_opts, key="cf_reason")
        notice_opts = ["Serving Notice", "Immediate Exit"]
        notice_type = st.selectbox("Notice Type *", notice_opts, key="cf_notice")

    with c2:
        sub_opts   = [""] + SUB_REASONS.get(sep_reason, [])
        # Reset sub if it doesn't belong to current reason
        if st.session_state.get("cf_sub") not in sub_opts:
            st.session_state["cf_sub"] = ""
        sub_reason   = st.selectbox("Separation Sub Reason *", sub_opts, key="cf_sub",
                                     disabled=not sep_reason,
                                     help="Select Separation Reason first" if not sep_reason else "")
        garden_opts  = ["No","Yes","NA"]
        garden_leave = st.selectbox("Garden Leave *", garden_opts, key="cf_garden")
        comm_opts    = [""] + COMMUNICATION_STATUSES
        comm_status  = st.selectbox("Communication Status *", comm_opts, key="cf_comm")

    existing_url  = edit_case.get("approval_file_url","")  if is_edit else ""
    existing_name = edit_case.get("approval_file_name","") if is_edit else ""
    if existing_url:
        st.markdown(f"📎 [Existing Approval Doc: {existing_name or 'View'}]({existing_url})")

    remarks       = st.text_area("Remarks / Exception", key="cf_rem")
    approval_file = st.file_uploader("Upload Approval PDF", type=["pdf","jpg","jpeg","png"], key="cf_file")

    if remarks and not approval_file and not existing_url:
        st.warning("Approval document required when remarks are entered.")

    # ── Live calculations — show as user fills form ───────────────────────────
    if sep_reason and dor and lwd and lwd >= dor:
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
    else:
        if sep_reason and dor and lwd:
            st.error("LWD cannot be before Date of Resignation — calculations hidden.")

    st.divider()

    # ── Submit ────────────────────────────────────────────────────────────────
    if st.button("Submit Case", type="primary", use_container_width=True):
        err = []
        if not dor:         err.append("Date of Resignation")
        if not lwd:         err.append("Last Working Date")
        if not sep_reason:  err.append("Separation Reason")
        if not sub_reason:  err.append("Separation Sub Reason")
        if not comm_status: err.append("Communication Status")
        if err:
            st.error(f"Missing: {', '.join(err)}")
            return
        if lwd < dor:
            st.error("LWD cannot be before DOR.")
            return
        if lwd < date.today():
            st.error("LWD cannot be a past date.")
            return
        if remarks and not approval_file and not existing_url:
            st.error("Approval document required when remarks are entered.")
            return

        calc = calculate_case(emp, {
            "last_working_date":               str(lwd),
            "date_of_resignation":             str(dor),
            "separation_reason":               sep_reason,
            "immediate_exit_or_serving_notice": notice_type,
        })

        old_status = edit_case.get("status","") if is_edit else ""
        new_status = ("Submitted" if comm_status == "Completed"
                      else "Sent Back" if old_status.lower() in ("sent back","sentback")
                      else "Pending" if comm_status in ("","Pending") else "Hold")

        emp_fields = [
            "emp_code","entity","business_unit","lob","function","sub_function",
            "region","site_name","grade","band","external_designation","internal_designation",
            "l1_manager","l1_manager_email","l2_manager","l2_manager_email",
            "hrbp_name","hrbp_mail_id","doj","group_doj","employee_status","gender",
            "fixed_ctc","variable","pli","retention","total_ctc",
            "monthly_gross","provident_fund","gratuity","medical_insurance",
        ]
        case_data = {
            **{k: emp.get(k) for k in emp_fields},
            "emp_name": emp.get("full_name",""), "official_email": emp.get("company_email_id",""),
            "personal_email": emp.get("personal_email_id",""), "personal_contact": emp.get("personal_mobile_no",""),
            "date_of_resignation": str(dor), "last_working_date": str(lwd),
            "separation_reason": sep_reason, "separation_sub_reason": sub_reason,
            "immediate_exit_or_serving_notice": notice_type, "garden_leave": garden_leave,
            "communication_status": comm_status, "remarks": remarks,
            "status": new_status, "created_by": user_email, "created_by_role": "MANAGER",
            **calc,
        }
        if is_edit:
            for f in ["admin_remarks","admin_action","admin_action_status","admin_closed_status",
                      "admin_closed_at","admin_closed_by","closure_status","payroll_downloaded_at",
                      "email_sent","email_sent_at","email_sent_status","created_at","created_by","created_by_role"]:
                if f in edit_case:
                    case_data[f] = edit_case[f]
            if old_status.lower() in ("sent back","sentback"):
                for f in ("admin_action","sent_back_at","sent_back_by"):
                    case_data[f] = ""

        with st.spinner("Saving…"):
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
                    update_case(case_id, {"approval_file_url":"","approval_file_name":""})
                log_audit("CASE_UPDATED", case_id, user_email)
                st.success(f"Case **{case_id}** updated!")
            else:
                created = create_case(case_data)
                if not created:
                    st.error("Failed to create case.")
                    return
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
                st.success(f"Case **{case_id}** created!")

        # Clean up and go back
        for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
            st.session_state.pop(k, None)
        st.rerun()


# ── Case summary (read-only) ───────────────────────────────────────────────────

def _case_summary(c: dict):
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**DOR:** {c.get('date_of_resignation','')}  |  **LWD:** {c.get('last_working_date','')}")
        st.write(f"**Reason:** {c.get('separation_reason','')} — {c.get('separation_sub_reason','')}")
        st.write(f"**Notice:** {c.get('immediate_exit_or_serving_notice','')}  |  **Garden Leave:** {c.get('garden_leave','')}")
    with c2:
        st.write(f"**Monthly Fixed Gross:** {_inr(c.get('monthly_fixed_gross'))}")
        st.write(f"**Severance Pay:** {_inr(c.get('severance_pay_amount'))} ({c.get('severance_days',0)} days)")
        st.write(f"**Notice Pay:** {_inr(c.get('notice_period_amount'))} ({c.get('notice_period_days',0)} days)")
    if c.get("approval_file_url"):
        st.link_button("📎 View Approval Document", c["approval_file_url"])
    if c.get("admin_remarks"):
        st.info(f"Admin remarks: {c['admin_remarks']}")


# ── Shared render functions ────────────────────────────────────────────────────

def render_my_team(user_email: str):
    try:
        employees = get_employees_for_manager(user_email)
    except Exception as e:
        st.error(f"Could not load team: {e}")
        return

    if not employees:
        st.info("No active direct reports found. Ask Admin → Employee Data & Sync → Sync from Darwinbox.")
        return

    st.caption(f"{len(employees)} active direct report(s)")
    hdr = st.columns([3,2,2,2,1.5])
    for h, t in zip(hdr, ["Name","Designation","Grade","Entity","Action"]):
        h.markdown(f"**{t}**")
    st.divider()

    for emp in employees:
        cols = st.columns([3,2,2,2,1.5])
        cols[0].write(f"**{emp['full_name']}**")
        cols[1].write(emp.get("external_designation",""))
        cols[2].write(emp.get("grade",""))
        cols[3].write(emp.get("entity",""))
        if cols[4].button("Open", key=f"open_{emp['emp_code']}"):
            # Clear old form state
            for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
                st.session_state.pop(k, None)
            st.session_state["cf_active_emp"]  = emp
            st.session_state["cf_edit_case"]   = None
            st.rerun()


def render_my_cases(user_email: str):
    try:
        cases = get_cases_for_manager(user_email)
    except Exception as e:
        st.error(f"Error loading cases: {e}")
        return

    if not cases:
        st.info("No separation cases created yet.")
        return

    STATUS_ICON = {"Pending":"🟡","Hold":"🟠","Submitted":"🔵","Sent Back":"🔴","Admin Closed":"🟢"}

    for case in cases:
        icon = STATUS_ICON.get(case.get("status",""), "⚪")
        editable = (
            str(case.get("closure_status","")).lower() != "closed" and
            case.get("status","").lower() in ("pending","hold","sent back","sentback")
        )
        with st.expander(f"{icon} **{case['case_id']}** — {case.get('emp_name','')} — LWD: {case.get('last_working_date','')}"):
            _case_summary(case)
            if editable:
                if st.button("Edit Case", key=f"edit_{case['case_id']}"):
                    emp_from_case = {
                        "full_name": case.get("emp_name",""), "emp_code": case.get("emp_code",""),
                        "company_email_id": case.get("official_email",""),
                        "personal_email_id": case.get("personal_email",""),
                        "personal_mobile_no": case.get("personal_contact",""),
                        **{k: case.get(k,"") for k in [
                            "entity","business_unit","lob","function","sub_function","region",
                            "site_name","grade","band","external_designation","internal_designation",
                            "l1_manager","l1_manager_email","l2_manager","l2_manager_email",
                            "hrbp_name","hrbp_mail_id","doj","group_doj","employee_status","gender",
                            "fixed_ctc","variable","pli","retention","total_ctc",
                            "monthly_gross","provident_fund","gratuity","medical_insurance",
                        ]},
                    }
                    for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
                        st.session_state.pop(k, None)
                    st.session_state["cf_active_emp"] = emp_from_case
                    st.session_state["cf_edit_case"]  = case
                    st.rerun()


# ── Manager dashboard ──────────────────────────────────────────────────────────

def manager_dashboard(user_email: str):
    # Form renders ABOVE tabs — no duplicate key issue
    if st.session_state.get("cf_active_emp"):
        emp       = st.session_state["cf_active_emp"]
        edit_case = st.session_state.get("cf_edit_case")
        if st.button("← Back"):
            for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
                st.session_state.pop(k, None)
            st.rerun()
        _render_case_form(emp, user_email, edit_case)
        return   # Don't show tabs while form is active

    # Normal view — tabs only when no form is active
    st.subheader("My Dashboard")
    tab1, tab2 = st.tabs(["My Team", "My Cases"])
    with tab1:
        render_my_team(user_email)
    with tab2:
        render_my_cases(user_email)
