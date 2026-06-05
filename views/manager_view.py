import streamlit as st
from datetime import date
from lib.sheets import get_employees_for_manager
from lib.db import (
    get_cases_for_manager, create_case, update_case,
    log_audit, get_client,
    SEPARATION_REASONS, SUB_REASONS, COMMUNICATION_STATUSES,
)
from lib.calculations import calculate_case, _parse_date as _pd


# ── Design system ──────────────────────────────────────────────────────────────

_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

.stApp, .stMarkdown, .stTextInput input, .stSelectbox select,
.stTextArea textarea, .stDateInput input, .stButton button,
.stFileUploader, .stCaption, .stSubheader {
  font-family: 'Plus Jakarta Sans', sans-serif !important;
}
.stButton > button[kind="primary"] {
  background: #4736FE !important;
  border: none !important;
  font-weight: 800 !important;
  border-radius: 9px !important;
}
.stButton > button[kind="primary"]:hover {
  background: #3628e0 !important;
  box-shadow: 0 3px 12px rgba(71,54,254,.3) !important;
}
.stButton > button:not([kind="primary"]) {
  font-weight: 600 !important;
  border-radius: 8px !important;
}
.stTabs [data-baseweb="tab"] {
  font-family: 'Plus Jakarta Sans', sans-serif !important;
  font-weight: 600 !important;
}
.stTabs [aria-selected="true"] { color: #4736FE !important; }
.stTabs [data-baseweb="tab-highlight"] { background: #4736FE !important; }
</style>"""


def _inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _inr(v):
    try:
        return f"₹{float(v):,.0f}"
    except (ValueError, TypeError):
        return "₹0"


def _avatar(name: str, size: int = 34) -> str:
    initials = "".join(w[0].upper() for w in str(name).split() if w)[:2] or "?"
    fs = max(10, size // 3)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:#EEF0FF;color:#4736FE;font-size:{fs}px;font-weight:800;'
        f'display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;">'
        f'{initials}</div>'
    )


def _section(title, color="default", icon=""):
    COLORS = {
        "blue":    ("#1D4ED8", "#BFDBFE"),
        "amber":   ("#92400E", "#FDE68A"),
        "green":   ("#059669", "#BBF7D0"),
        "purple":  ("#5B21B6", "#DDD6FE"),
        "default": ("#9CA3AF", "#F3F4F6"),
    }
    clr, border = COLORS.get(color, COLORS["default"])
    prefix = f"{icon}&nbsp;" if icon else ""
    st.markdown(
        f'<div style="font-family:\'Plus Jakarta Sans\',sans-serif;font-size:10px;font-weight:800;'
        f'text-transform:uppercase;letter-spacing:.7px;color:{clr};margin:16px 0 10px 0;'
        f'padding-bottom:8px;border-bottom:1px solid {border};">{prefix}{title}</div>',
        unsafe_allow_html=True,
    )


def _chip(status):
    S = {
        "Pending":       ("#FFFBEB", "#92400E"),
        "Hold":          ("#FEF2F2", "#991B1B"),
        "Submitted":     ("#EFF6FF", "#1D4ED8"),
        "Sent Back":     ("#FCE7F3", "#9D174D"),
        "Admin Closed":  ("#ECFDF5", "#065F46"),
        "FNF Processed": ("#ECFDF5", "#065F46"),
    }
    bg, fg = S.get(str(status), ("#F3F4F6", "#6B7280"))
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 9px;'
        f'border-radius:999px;font-size:10.5px;font-weight:700;">{status}</span>'
    )


def _calc_cards(items):
    tiles = "".join(
        f'<div style="background:#ECFDF5;border:1px solid #A7F3D0;border-radius:8px;'
        f'padding:10px 6px;text-align:center;">'
        f'<div style="font-size:9px;color:#065F46;font-weight:800;text-transform:uppercase;'
        f'letter-spacing:.4px;margin-bottom:4px;">{lbl}</div>'
        f'<div style="font-size:14px;font-weight:800;color:#14532D;">{val}</div></div>'
        for lbl, val in items
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);'
        f'gap:8px;margin-bottom:10px;">{tiles}</div>',
        unsafe_allow_html=True,
    )


def _amount_cards(items):
    tiles = "".join(
        f'<div style="background:#DCFCE7;border:1px solid #86EFAC;border-radius:8px;'
        f'padding:11px 8px;text-align:center;">'
        f'<div style="font-size:9px;color:#14532D;font-weight:800;text-transform:uppercase;'
        f'letter-spacing:.4px;margin-bottom:4px;">{lbl}</div>'
        f'<div style="font-size:15px;font-weight:800;color:#15803D;">{val}</div></div>'
        for lbl, val in items
    )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">{tiles}</div>',
        unsafe_allow_html=True,
    )


def _upload_file(file, case_id):
    sb   = get_client()
    path = f"cases/{case_id}/{file.name}"
    sb.storage.from_("attachments").upload(path, file.getvalue(), {"content-type": file.type or "application/pdf"})
    return sb.storage.from_("attachments").get_public_url(path), file.name


# ── Case form ──────────────────────────────────────────────────────────────────

def _render_case_form(emp: dict, user_email: str, edit_case: dict = None):
    is_edit  = edit_case is not None
    emp_code = emp.get("emp_code", "")
    name     = emp.get("full_name", "")

    # One-time init
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

    # ── Dark form header ───────────────────────────────────────────────────────
    initials = "".join(w[0].upper() for w in name.split() if w)[:2] or "?"
    action   = "Edit Separation" if is_edit else "Initiate Separation"
    st.markdown(
        f'<div style="background:#0F0E1A;padding:16px 20px;border-radius:10px 10px 0 0;'
        f'display:flex;align-items:center;gap:14px;margin-bottom:0;">'
        f'<div style="width:42px;height:42px;border-radius:50%;background:rgba(71,54,254,.2);'
        f'color:#7B6FFF;font-size:15px;font-weight:800;display:flex;align-items:center;'
        f'justify-content:center;flex-shrink:0;">{initials}</div>'
        f'<div><div style="color:#fff;font-size:15px;font-weight:800;'
        f'font-family:\'Plus Jakarta Sans\',sans-serif;">{action} — {name}</div>'
        f'<div style="color:#6B7280;font-size:12px;margin-top:2px;">'
        f'{emp_code} · {emp.get("external_designation","")} · '
        f'{emp.get("grade","")} · {emp.get("entity","")}'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    # ── Two-column layout ──────────────────────────────────────────────────────
    left, right = st.columns([1, 1], gap="large")

    with left:
        _section("Case Inputs", "amber", "📝")

        dor = st.date_input("Date of Resignation *", key="cf_dor")
        lwd = st.date_input("Last Working Date *", key="cf_lwd",
                             min_value=date.today(), help="Past dates are greyed out")

        if lwd and dor and lwd < dor:
            st.error("LWD cannot be before Date of Resignation.")

        reason_opts = [""] + SEPARATION_REASONS
        sep_reason  = st.selectbox("Separation Reason *", reason_opts, key="cf_reason")

        sub_opts = [""] + SUB_REASONS.get(sep_reason, [])
        if st.session_state.get("cf_sub") not in sub_opts:
            st.session_state["cf_sub"] = ""
        sub_reason = st.selectbox("Separation Sub Reason *", sub_opts, key="cf_sub",
                                   disabled=not sep_reason,
                                   help="Select Separation Reason first" if not sep_reason else "")

        notice_opts = ["Serving Notice", "Immediate Exit"]
        notice_type = st.selectbox("Notice Type *", notice_opts, key="cf_notice")

        garden_opts  = ["No", "Yes", "NA"]
        garden_leave = st.selectbox("Garden Leave *", garden_opts, key="cf_garden")

        comm_opts   = [""] + COMMUNICATION_STATUSES
        comm_status = st.selectbox("Communication Status *", comm_opts, key="cf_comm")

        existing_url  = edit_case.get("approval_file_url","")  if is_edit else ""
        existing_name = edit_case.get("approval_file_name","") if is_edit else ""
        if existing_url:
            st.markdown(f"📎 [Existing Approval Doc: {existing_name or 'View'}]({existing_url})")

        remarks       = st.text_area("Remarks / Exception", key="cf_rem")
        approval_file = st.file_uploader("Upload Approval PDF", type=["pdf","jpg","jpeg","png"], key="cf_file")

        if remarks and not approval_file and not existing_url:
            st.warning("Approval document required when remarks are entered.")

    with right:
        # ── Employee card ──────────────────────────────────────────────────────
        _section("Employee Profile", "blue", "👤")
        doj = emp.get("group_doj","") or emp.get("doj","")
        meta_rows = [
            ("Grade / Band",   f'{emp.get("grade","")} / {emp.get("band","")}'),
            ("Entity",         emp.get("entity","")),
            ("Date of Joining", doj),
            ("HRBP",           emp.get("hrbp_name","")),
            ("L1 Manager",     emp.get("l1_manager","")),
            ("L2 Manager",     emp.get("l2_manager","")),
        ]
        meta_html = "".join(
            f'<div><div style="font-size:9.5px;font-weight:700;color:#9CA3AF;'
            f'text-transform:uppercase;letter-spacing:.4px;margin-bottom:2px;">{lbl}</div>'
            f'<div style="font-size:12px;color:#374151;font-weight:600;">{val or "—"}</div></div>'
            for lbl, val in meta_rows
        )
        st.markdown(
            f'<div style="background:#fff;border:1px solid #E5E7EB;border-radius:10px;'
            f'padding:14px;margin-bottom:4px;">'
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">'
            f'{_avatar(name, 40)}'
            f'<div><div style="font-size:14px;font-weight:800;color:#111827;'
            f'font-family:\'Plus Jakarta Sans\',sans-serif;">{name}</div>'
            f'<div style="font-size:11.5px;color:#6B7280;margin-top:1px;">'
            f'{emp.get("external_designation","")} · {emp_code}</div></div></div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">'
            f'{meta_html}</div></div>',
            unsafe_allow_html=True,
        )

        # ── Live calculations (logic untouched, only display updated) ──────────
        if sep_reason and dor and lwd and lwd >= dor:
            calc = calculate_case(emp, {
                "last_working_date":                str(lwd),
                "date_of_resignation":              str(dor),
                "separation_reason":                sep_reason,
                "immediate_exit_or_serving_notice": notice_type,
            })
            _section("Live Calculations", "green", "⚡")
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
        elif sep_reason and dor and lwd and lwd < dor:
            st.error("LWD cannot be before DOR — calculations hidden.")
        else:
            st.markdown(
                '<div style="background:#F9FAFB;border:1.5px dashed #E5E7EB;border-radius:8px;'
                'padding:24px;text-align:center;color:#9CA3AF;font-size:13px;margin-top:8px;">'
                '⚡ Fill in Dates + Separation Reason<br/>to see live calculations</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Submit ─────────────────────────────────────────────────────────────────
    if st.button("✓  Submit Separation Case", type="primary", use_container_width=True):
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

        for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
            st.session_state.pop(k, None)
        st.rerun()


# ── Case summary (read-only) ───────────────────────────────────────────────────

def _case_summary(c: dict):
    st.markdown(_chip(c.get("status","")), unsafe_allow_html=True)
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

    # Table header
    st.markdown(
        '<div style="display:grid;grid-template-columns:2.5fr 2fr 1fr 1.5fr 110px;'
        'padding:10px 12px;background:#FAFAFA;border:1px solid #E5E7EB;'
        'border-radius:10px 10px 0 0;font-size:10.5px;font-weight:700;'
        'text-transform:uppercase;letter-spacing:.5px;color:#9CA3AF;">'
        '<div>Employee</div><div>Designation</div><div>Grade</div>'
        '<div>Entity</div><div>Action</div></div>',
        unsafe_allow_html=True,
    )

    for emp in employees:
        cols = st.columns([2.5, 2, 1, 1.5, 1.1])
        with cols[0]:
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:6px 0;">'
                f'{_avatar(emp["full_name"])}'
                f'<div><div style="font-weight:700;color:#111827;font-size:13px;">{emp["full_name"]}</div>'
                f'<div style="font-size:11px;color:#9CA3AF;">{emp.get("emp_code","")}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        cols[1].write(emp.get("external_designation",""))
        cols[2].markdown(
            f'<span style="background:#EFF6FF;color:#1D4ED8;padding:2px 9px;'
            f'border-radius:999px;font-size:11px;font-weight:700;">'
            f'{emp.get("grade","")}</span>',
            unsafe_allow_html=True,
        )
        cols[3].write(emp.get("entity",""))
        if cols[4].button("Open →", key=f"open_{emp['emp_code']}"):
            for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
                st.session_state.pop(k, None)
            st.session_state["cf_active_emp"] = emp
            st.session_state["cf_edit_case"]  = None
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
        icon     = STATUS_ICON.get(case.get("status",""), "⚪")
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
    _inject_css()

    if st.session_state.get("cf_active_emp"):
        emp       = st.session_state["cf_active_emp"]
        edit_case = st.session_state.get("cf_edit_case")
        if st.button("← Back"):
            for k in [k for k in st.session_state if k.startswith("cf_") or k.startswith("_cf_")]:
                st.session_state.pop(k, None)
            st.rerun()
        _render_case_form(emp, user_email, edit_case)
        return

    st.subheader("My Dashboard")
    tab1, tab2 = st.tabs(["My Team", "My Cases"])
    with tab1:
        render_my_team(user_email)
    with tab2:
        render_my_cases(user_email)
