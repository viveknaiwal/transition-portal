# Python port of lib/darwinbox.ts — fetches employee master from Darwinbox API
import os
import re
import base64
from datetime import date
import requests
from dotenv import load_dotenv

load_dotenv()

DB_BASE      = "https://cars24.darwinbox.in"
MASTER_URL   = f"{DB_BASE}/masterapi/employee"
LWD_CUTOFF   = date(2026, 3, 31)   # include separated employees only after this date


def _basic_auth():
    u = os.getenv("DARWINBOX_USERNAME", "")
    p = os.getenv("DARWINBOX_PASSWORD", "")
    return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()


def _parse_emp_id(raw):
    if not raw:
        return None
    m = re.search(r'\((\d+)\)', str(raw))
    return m.group(1) if m else None


def _parse_name(raw):
    if not raw:
        return ""
    return re.sub(r'\s*\(\d+\)\s*$', '', str(raw)).strip()


def _find_field(obj: dict, *keys):
    for k in keys:
        clean_k = k.lower().replace(" ", "")
        for bk, v in obj.items():
            if clean_k in bk.lower().replace("_", "").replace(" ", ""):
                try:
                    n = float(v)
                    if n > 0:
                        return n
                except (ValueError, TypeError):
                    pass
    return 0.0


def _parse_date_str(v) -> date | None:
    if not v:
        return None
    s = str(v).strip()
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _should_include(r: dict) -> bool:
    """Include Active employees (blank LWD) + those who left after LWD_CUTOFF."""
    status = str(r.get("employee_status", "")).strip().lower()
    if status == "active":
        return True
    # Check any date-of-leaving field Darwinbox might use
    lwd_val = (
        r.get("date_of_leaving") or
        r.get("exit_date") or
        r.get("last_working_day") or
        r.get("date_of_exit") or
        r.get("resignation_date") or ""
    )
    lwd = _parse_date_str(lwd_val)
    return bool(lwd and lwd > LWD_CUTOFF)


def test_connection() -> dict:
    """Returns raw API diagnostic info — use from admin UI to debug response format."""
    api_key     = os.getenv("DARWINBOX_MASTER_API_KEY", "")
    dataset_key = os.getenv("DARWINBOX_DATASET_KEY", "")
    headers     = {"Content-Type": "application/json", "Authorization": _basic_auth()}
    try:
        resp = requests.post(
            MASTER_URL,
            json={"api_key": api_key, "datasetKey": dataset_key},
            headers=headers,
            timeout=30,
        )
        info = {"http_status": resp.status_code}
        try:
            j = resp.json()
            info["response_type"] = type(j).__name__
            if isinstance(j, list):
                info["format"]            = "list"
                info["total_records"]     = len(j)
                info["first_record_keys"] = list(j[0].keys())[:30] if j else []
            elif isinstance(j, dict):
                info["format"]          = "dict"
                info["top_level_keys"]  = list(j.keys())
                # Find the list inside
                for k, v in j.items():
                    if isinstance(v, list) and v:
                        info["list_key"]          = k
                        info["total_records"]     = len(v)
                        info["first_record_keys"] = list(v[0].keys())[:30]
                        # CTC fields
                        info["ctc_fields"] = [fk for fk in v[0].keys() if "ctc" in fk.lower()]
                        break
            else:
                info["raw_preview"] = str(j)[:500]
        except Exception as e:
            info["parse_error"] = str(e)
            info["raw_text"]    = resp.text[:500]
        return info
    except Exception as e:
        return {"error": str(e)}


def fetch_employee_master() -> list[dict]:
    api_key     = os.getenv("DARWINBOX_MASTER_API_KEY", "")
    dataset_key = os.getenv("DARWINBOX_DATASET_KEY", "")

    headers = {
        "Content-Type": "application/json",
        "Authorization": _basic_auth(),
    }
    resp = requests.post(
        MASTER_URL,
        json={"api_key": api_key, "datasetKey": dataset_key},
        headers=headers,
        timeout=120,
    )
    resp.raise_for_status()
    json_data = resp.json()

    # Handle all known Darwinbox response formats
    if isinstance(json_data, list):
        raw_list = json_data
    elif isinstance(json_data, dict):
        # Try every known key name
        raw_list = []
        # employee_data is the actual Darwinbox master API key (confirmed from Code.gs)
        for key in ["employee_data", "data", "employees", "result", "employee_details",
                    "records", "items", "employeeData", "EmployeeData", "Data", "Results"]:
            val = json_data.get(key)
            if isinstance(val, list) and val:
                raw_list = val
                break
        if not raw_list:
            # dict-of-dicts format: {"0": {...}, "1": {...}}
            all_vals = [v for v in json_data.values() if isinstance(v, dict)]
            if all_vals:
                raw_list = all_vals
    else:
        raw_list = []

    if not raw_list:
        raise ValueError(
            f"Darwinbox returned empty employee list. "
            f"Response type: {type(json_data).__name__}. "
            f"Keys: {list(json_data.keys()) if isinstance(json_data, dict) else 'N/A'}. "
            f"Use 'Test API Connection' in the Sync tab to inspect the raw response."
        )

    total_before = len(raw_list)
    raw_list = [r for r in raw_list if _should_include(r)]
    print(f"Darwinbox: {total_before} total → {len(raw_list)} after filter (Active + left after {LWD_CUTOFF})")

    # Build id → email / name maps for manager + HRBP resolution
    id_to_email: dict[str, str] = {}
    id_to_name:  dict[str, str] = {}
    for r in raw_list:
        eid   = str(r.get("employee_id") or r.get("employeeId") or "")
        email = str(r.get("company_email_id") or r.get("email") or "").lower().strip()
        name  = str(r.get("full_name") or r.get("name") or "").strip()
        if eid:
            id_to_email[eid] = email
            id_to_name[eid]  = name

    employees = []
    for r in raw_list:
        emp_id = str(r.get("employee_id") or r.get("employeeId") or "")

        # CTC breakup fields (flat prefixed keys or nested object)
        breakup: dict = {}
        for k, v in r.items():
            if k.startswith("ctc_ctc_break_up") or k.startswith("ctc_break_up"):
                short = re.sub(r'^ctc_ctc_break_up\.?|^ctc_break_up\.?', '', k)
                breakup[short] = v
        nested = r.get("ctc_ctc_break_up") or r.get("ctc_break_up") or {}
        if isinstance(nested, dict):
            breakup.update(nested)

        l1_raw_id = _parse_emp_id(r.get("direct_manager"))
        l1_email  = id_to_email.get(l1_raw_id, "") if l1_raw_id else ""
        l1_name   = (
            id_to_name.get(l1_raw_id, _parse_name(r.get("direct_manager")))
            if l1_raw_id else _parse_name(r.get("direct_manager"))
        )

        l2_name = l2_email = ""
        if l1_raw_id:
            l1_raw = next(
                (e for e in raw_list
                 if str(e.get("employee_id") or e.get("employeeId") or "") == l1_raw_id),
                None,
            )
            if l1_raw:
                l2_raw_id = _parse_emp_id(l1_raw.get("direct_manager"))
                if l2_raw_id:
                    l2_name  = id_to_name.get(l2_raw_id, _parse_name(l1_raw.get("direct_manager")))
                    l2_email = id_to_email.get(l2_raw_id, "")

        hrbp_raw_id = _parse_emp_id(r.get("hrbp_role"))
        hrbp_email  = id_to_email.get(hrbp_raw_id, "") if hrbp_raw_id else ""
        hrbp_name   = _parse_name(r.get("hrbp_role"))

        fixed_ctc  = float(r.get("ctc_fixed_ctc") or 0)
        var_pay    = float(r.get("ctc_variable_pay") or 0)
        total_ctc  = float(r.get("ctc_ctc_total") or 0)
        pf         = _find_field(breakup, "providentfund", "pf", "epf")
        gratuity   = _find_field(breakup, "gratuity")
        medical    = _find_field(breakup, "mediclaim", "medical", "insurance")
        monthly_gross = (total_ctc - gratuity - pf - medical) / 12 if total_ctc > 0 else 0

        employees.append({
            "employee_id":          emp_id,
            "emp_code":             emp_id,
            "full_name":            str(r.get("full_name") or r.get("name") or "").strip(),
            "company_email_id":     str(r.get("company_email_id") or "").lower().strip(),
            "personal_email_id":    str(r.get("personal_email_id") or "").strip(),
            "personal_mobile_no":   str(r.get("personal_mobile_no") or r.get("office_mobile_no") or "").strip(),
            "entity":               str(r.get("group_company") or "").strip(),
            "business_unit":        str(r.get("business_unit") or "").strip(),
            "lob":                  str(r.get("business_lob_/_soh") or r.get("business_lob") or "").strip(),
            "function":             str(r.get("top_department") or r.get("department") or "").strip(),
            "sub_function":         str(r.get("sub-function") or r.get("sub_function") or "").strip(),
            "region":               str(r.get("central/regional") or r.get("region") or "").strip(),
            "site_name":            str(r.get("office_location") or "").strip(),
            "grade":                str(r.get("job_level") or "").strip(),
            "band":                 str(r.get("band") or "").strip(),
            "external_designation": str(r.get("designation") or "").strip(),
            "internal_designation": str(r.get("job_level") or r.get("designation") or "").strip(),
            "l1_manager":           l1_name,
            "l1_manager_email":     l1_email,
            "l2_manager":           l2_name,
            "l2_manager_email":     l2_email,
            "hrbp_name":            hrbp_name,
            "hrbp_mail_id":         hrbp_email,
            "doj":                  str(r.get("date_of_joining") or "").strip(),
            "group_doj":            str(r.get("group_date_of_joining") or r.get("date_of_joining") or "").strip(),
            "employee_status":      str(r.get("employee_status") or "").strip(),
            "gender":               str(r.get("gender") or "").strip(),
            "fixed_ctc":            fixed_ctc,
            "variable":             var_pay,
            "pli":                  0,
            "retention":            0,
            "total_ctc":            total_ctc,
            "monthly_gross":        round(monthly_gross),
            "provident_fund":       pf,
            "gratuity":             gratuity,
            "medical_insurance":    medical,
            "email_check":          str(r.get("company_email_id") or "").lower().strip(),
        })

    return employees
