# Reads employee + CTC data from the hr-dashboard Consolidated_Base Google Sheet.
# The sheet is synced daily (7 AM) from Darwinbox master + payroll APIs via Code.gs.
# This avoids hitting Darwinbox APIs directly from the transition portal.

import os
import re
import requests
import pandas as pd
from io import StringIO
from dotenv import load_dotenv

load_dotenv()

LWD_CUTOFF = "2026-03-31"   # include separated employees only if they left after this date


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_emp_id(raw: str) -> str:
    m = re.search(r'\((\d+)\)', str(raw or ""))
    return m.group(1) if m else ""

def _parse_name(raw: str) -> str:
    return re.sub(r'\s*\(\d+\)\s*$', '', str(raw or "")).strip()

def _num(v) -> float:
    try:
        return float(str(v or 0).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0

def _g(row: dict, *keys) -> str:
    """Get first non-empty value from a list of possible column names (case-insensitive)."""
    for k in keys:
        v = str(row.get(k.lower(), "") or "").strip()
        if v and v.lower() not in ("-", "na", "n/a", "null", "none", ""):
            return v
    return ""

def _should_include(row: dict) -> bool:
    status = _g(row, "employee_status").lower()
    if status == "active":
        return True
    exit_date = _g(row, "date_of_exit", "date_of_leaving", "date_of_exit")
    if exit_date and exit_date[:10] > LWD_CUTOFF:
        return True
    return False


# ── Main fetch ─────────────────────────────────────────────────────────────────

def fetch_from_sheet() -> list[dict]:
    url = os.getenv("GOOGLE_SHEET_CSV_URL", "").strip()
    if not url:
        raise ValueError(
            "GOOGLE_SHEET_CSV_URL not set.\n"
            "Steps: Open hr-dashboard Google Sheet → File → Share → Publish to web "
            "→ Sheet: Consolidated_Base → Format: CSV → Publish → copy URL → add to .env"
        )

    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text), dtype=str).fillna("")

    # Normalize all column names to lowercase + stripped
    df.columns = [c.strip().lower() for c in df.columns]
    cols = set(df.columns)

    # Build employee ID → email/name lookup for manager + HRBP resolution
    id_to_email: dict[str, str] = {}
    id_to_name:  dict[str, str] = {}
    id_to_row:   dict[str, dict] = {}

    for row in df.to_dict("records"):
        eid = _g(row, "employee_id", "employeeid", "emp_code")
        if eid:
            id_to_email[eid] = _g(row, "company_email_id", "email", "official_email").lower()
            id_to_name[eid]  = _g(row, "employee_full_name", "full_name", "name")
            id_to_row[eid]   = row

    employees = []
    skipped   = 0

    for row in df.to_dict("records"):
        if not _should_include(row):
            skipped += 1
            continue

        emp_id = _g(row, "employee_id", "employeeid", "emp_code")
        if not emp_id or not re.match(r'^\d{4,}$', emp_id):
            continue

        # ── L1 Manager ──────────────────────────────────────────
        l1_raw_id = (
            _g(row, "reporting_manager_employee_id", "direct_manager_employee_id",
               "manager_employee_id", "reporting_manager_id") or
            _parse_emp_id(_g(row, "direct_manager", "reporting_manager"))
        )
        l1_email = id_to_email.get(l1_raw_id, "")
        l1_name  = id_to_name.get(l1_raw_id, _parse_name(_g(row, "direct_manager", "reporting_manager"))) if l1_raw_id else _parse_name(_g(row, "direct_manager"))

        # ── L2 Manager ──────────────────────────────────────────
        l2_name = l2_email = ""
        if l1_raw_id and l1_raw_id in id_to_row:
            l1r       = id_to_row[l1_raw_id]
            l2_raw_id = (
                _g(l1r, "reporting_manager_employee_id", "direct_manager_employee_id") or
                _parse_emp_id(_g(l1r, "direct_manager", "reporting_manager"))
            )
            if l2_raw_id:
                l2_name  = id_to_name.get(l2_raw_id, "")
                l2_email = id_to_email.get(l2_raw_id, "")

        # ── HRBP ────────────────────────────────────────────────
        hrbp_raw_id = _parse_emp_id(_g(row, "hrbp_role", "hrbp"))
        hrbp_email  = id_to_email.get(hrbp_raw_id, _g(row, "hrbp_mail_id", "hrbp_email"))
        hrbp_name   = _parse_name(_g(row, "hrbp_role", "hrbp_name"))

        # ── CTC fields (prefixed ctc_ in Consolidated_Base) ─────
        total_ctc = _num(_g(row, "ctc_ctc_total", "ctc_total_ctc", "ctc_annual_ctc"))
        fixed_ctc = _num(_g(row, "ctc_fixed_ctc", "ctc_fixed"))
        var_pay   = _num(_g(row, "ctc_variable_pay", "ctc_variable"))

        # CTC breakup for PF, Gratuity, Medical — sheet column format: ctc_ctc_break_up.fieldname
        def _ctc_bu(*field_names):
            for fname in field_names:
                v = _num(_g(row, f"ctc_ctc_break_up.{fname}", f"ctc_break_up.{fname}"))
                if v > 0:
                    return v
            return 0.0

        pf       = _ctc_bu("provident fund", "pf employer", "epf employer", "pf", "epf")
        gratuity = _ctc_bu("gratuity")
        medical  = _ctc_bu("mediclaim", "medical insurance", "medical")

        monthly_gross = (total_ctc - gratuity - pf - medical) / 12 if total_ctc > 0 else 0

        # ── DOJ: group_doj → doj fallback ───────────────────────
        group_doj = _g(row, "group_date_of_joining") or _g(row, "date_of_joining")
        doj       = _g(row, "date_of_joining")

        # designation: trimmed before "(" (same as GAS TRIM_BEFORE_PAREN)
        designation = _g(row, "designation", "external_designation").split("(")[0].strip()

        employees.append({
            "employee_id":          emp_id,
            "emp_code":             emp_id,
            "full_name":            _g(row, "employee_full_name", "full_name"),
            "company_email_id":     _g(row, "company_email_id", "email", "official_email").lower(),
            "personal_email_id":    _g(row, "personal_email_id"),
            "personal_mobile_no":   _g(row, "personal_mobile_no", "office_mobile_no"),
            "entity":               _g(row, "group_company", "entity"),
            "business_unit":        _g(row, "business_unit"),
            "lob":                  _g(row, "business_lob_/_soh", "business_lob"),
            "function":             _g(row, "top_department", "department", "function"),
            "sub_function":         _g(row, "sub-function", "sub_function"),
            "region":               _g(row, "central/regional", "region"),
            "site_name":            _g(row, "office_location", "site_name"),
            "grade":                _g(row, "job_level", "grade"),
            "band":                 _g(row, "band"),
            "external_designation": designation,
            "internal_designation": _g(row, "job_level", "designation"),
            "l1_manager":           l1_name,
            "l1_manager_email":     l1_email,
            "l2_manager":           l2_name,
            "l2_manager_email":     l2_email,
            "hrbp_name":            hrbp_name,
            "hrbp_mail_id":         hrbp_email,
            "doj":                  doj,
            "group_doj":            group_doj,
            "employee_status":      _g(row, "employee_status"),
            "gender":               _g(row, "gender"),
            "fixed_ctc":            fixed_ctc,
            "variable":             var_pay,
            "pli":                  0,
            "retention":            0,
            "total_ctc":            total_ctc,
            "monthly_gross":        round(monthly_gross),
            "provident_fund":       pf,
            "gratuity":             gratuity,
            "medical_insurance":    medical,
            "email_check":          _g(row, "company_email_id").lower(),
        })

    print(f"Sheet sync: {len(df)} total rows → {len(employees)} included ({skipped} filtered out)")
    return employees


def get_sheet_info() -> dict:
    """Diagnostic — shows sheet columns and CTC field names without syncing."""
    url = os.getenv("GOOGLE_SHEET_CSV_URL", "").strip()
    if not url:
        return {"error": "GOOGLE_SHEET_CSV_URL not set"}
    try:
        resp = requests.get(url, timeout=30)
        df   = pd.read_csv(StringIO(resp.text), dtype=str).fillna("")
        df.columns = [c.strip().lower() for c in df.columns]
        all_cols = list(df.columns)
        ctc_cols = [c for c in all_cols if c.startswith("ctc_")]
        return {
            "http_status":   resp.status_code,
            "total_rows":    len(df),
            "total_columns": len(all_cols),
            "ctc_columns":   ctc_cols[:20],
            "sample_columns": all_cols[:30],
        }
    except Exception as e:
        return {"error": str(e)}
