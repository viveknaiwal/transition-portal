# Darwinbox API client — employee master + payroll CTC (mirrors hr-dashboard Code.gs)
import os
import re
import base64
import requests
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

MASTER_URL  = "https://cars24.darwinbox.in/masterapi/employee"
PAYROLL_URL = "https://cars24.darwinbox.in/payrollapi/ctcbreakup"
LWD_CUTOFF  = date(2026, 3, 31)   # active + left after this date
BATCH_SIZE  = 500
CTC_FROM    = "01-01-2020"


# ── Auth ───────────────────────────────────────────────────────────────────────

def _auth() -> str:
    u = os.getenv("DARWINBOX_USERNAME", "")
    p = os.getenv("DARWINBOX_PASSWORD", "")
    return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()

def _headers() -> dict:
    return {"Content-Type": "application/json", "Authorization": _auth()}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _flatten(obj: dict, prefix: str = "", out: dict = None) -> dict:
    """Recursively flatten nested dicts (mirrors GAS flattenObject)."""
    if out is None:
        out = {}
    for k, v in (obj or {}).items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            _flatten(v, key, out)
        else:
            out[key] = v
    return out


def _extract_list(json_data) -> list:
    """Extract employee/CTC list from any Darwinbox response format."""
    if isinstance(json_data, list):
        return json_data
    if isinstance(json_data, dict):
        for key in ["employee_data", "ctc_data", "data", "employees",
                    "result", "results", "records", "employee_details"]:
            val = json_data.get(key)
            if isinstance(val, list) and val:
                return val
        # dict-of-dicts: {"0": {...}, "1": {...}}
        vals = [v for v in json_data.values() if isinstance(v, dict)]
        if vals:
            return vals
    return []


def _get_emp_code(obj: dict) -> str:
    for k in ["employee_id", "employee_no", "emp_code", "ecode", "employeeId"]:
        v = str(obj.get(k, "") or "").strip()
        if v and re.match(r'^\d{4,}$', v):
            return v
    return ""


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


def _parse_date(v) -> date | None:
    s = str(v or "").strip()
    if not s or s.lower() in ("-", "na", "n/a", "null", "none", "0000-00-00"):
        return None
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def _should_include(r: dict) -> bool:
    """Keep: active employees (no exit date) + those who left after LWD_CUTOFF."""
    status = str(r.get("employee_status", "")).strip().lower()
    exit_raw = str(r.get("date_of_exit") or r.get("date_of_leaving") or "").strip()

    if not exit_raw or exit_raw.lower() in ("", "-", "na", "n/a", "null", "none", "0000-00-00"):
        return True   # no exit date = still active

    d = _parse_date(exit_raw)
    if d is None:
        return status == "active"
    return d > LWD_CUTOFF


def _find(obj: dict, *keys) -> float:
    """Find first non-zero numeric value from a list of possible field names."""
    for k in keys:
        v = obj.get(k)
        if v is not None:
            n = _num(v)
            if n > 0:
                return n
    return 0.0


def _get_manager_id(row: dict) -> str:
    for field in ["reporting_manager_employee_id", "direct_manager_employee_id",
                  "manager_employee_id", "reporting_manager_id", "direct_manager_id"]:
        v = str(row.get(field, "") or "").strip()
        if v and re.match(r'^\d{4,}$', v):
            return v
    # "Firstname Lastname (12345)" format
    for field in ["direct_manager", "reporting_manager"]:
        pid = _parse_emp_id(str(row.get(field, "") or ""))
        if pid:
            return pid
    return ""


# ── CTC API ────────────────────────────────────────────────────────────────────

def fetch_ctc_data(emp_ids: list) -> dict:
    """Fetch payroll CTC in batches of 500. Returns {emp_code: flat_ctc_dict}."""
    api_key = os.getenv("DARWINBOX_PAYROLL_API_KEY", "")
    if not api_key:
        print("WARNING: DARWINBOX_PAYROLL_API_KEY not set — CTC will be 0")
        return {}

    ctc_map: dict = {}
    total   = len(emp_ids)
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, total, BATCH_SIZE):
        batch   = [str(e) for e in emp_ids[i:i + BATCH_SIZE]]
        payload = {
            "api_key":        api_key,
            "employee_no":    batch,
            "last_modified":  CTC_FROM,
            "proration_type": "monthly",
        }
        try:
            resp    = requests.post(PAYROLL_URL, json=payload, headers=_headers(), timeout=120)
            records = _extract_list(resp.json()) if resp.status_code == 200 else []
            for r in records:
                flat = _flatten(r)
                code = _get_emp_code(flat)
                if code:
                    ctc_map[code] = flat
            print(f"  CTC batch {i//BATCH_SIZE + 1}/{batches}: {len(records)} records")
        except Exception as e:
            print(f"  CTC batch {i//BATCH_SIZE + 1} error: {e}")

    print(f"CTC total: {len(ctc_map)} employees")
    return ctc_map


# ── Master API ─────────────────────────────────────────────────────────────────

def fetch_employee_master() -> list[dict]:
    """
    Fetch all employees from Darwinbox master API + payroll CTC API.
    Returns filtered list: active + left after 31 March 2026.
    With full CTC, manager chain, and HRBP resolved.
    """
    print("Fetching Darwinbox employee master…")
    resp = requests.post(
        MASTER_URL,
        json={
            "api_key":    os.getenv("DARWINBOX_MASTER_API_KEY", ""),
            "datasetKey": os.getenv("DARWINBOX_DATASET_KEY", ""),
        },
        headers=_headers(),
        timeout=120,
    )
    resp.raise_for_status()

    raw_list = [_flatten(r) for r in _extract_list(resp.json())]

    if not raw_list:
        j = resp.json()
        raise ValueError(
            f"Darwinbox master API returned no records. "
            f"Response type: {type(j).__name__}. "
            f"Keys: {list(j.keys()) if isinstance(j, dict) else 'N/A'}"
        )

    print(f"Master API: {len(raw_list)} total records received")

    # Filter by status / exit date
    filtered = [r for r in raw_list if _should_include(r)]
    print(f"After filter (active + left>{LWD_CUTOFF}): {len(filtered)} employees")

    if not filtered:
        raise ValueError(
            f"All {len(raw_list)} employees were filtered out. "
            f"Check employee_status values and date_of_exit fields."
        )

    # Build lookup maps from ALL records (needed for manager chain resolution)
    id_to_email: dict[str, str] = {}
    id_to_name:  dict[str, str] = {}
    id_to_row:   dict[str, dict] = {}
    for r in raw_list:
        eid = _get_emp_code(r)
        if eid:
            id_to_email[eid] = str(r.get("company_email_id") or r.get("email") or "").lower().strip()
            id_to_name[eid]  = str(r.get("employee_full_name") or r.get("full_name") or r.get("name") or "").strip()
            id_to_row[eid]   = r

    # Fetch CTC for filtered employees
    emp_ids = [_get_emp_code(r) for r in filtered if _get_emp_code(r)]
    ctc_map = fetch_ctc_data(emp_ids)

    employees = []
    for r in filtered:
        emp_id = _get_emp_code(r)
        if not emp_id:
            continue

        # L1 Manager
        l1_id    = _get_manager_id(r)
        l1_email = id_to_email.get(l1_id, "")
        l1_name  = id_to_name.get(l1_id, _parse_name(str(r.get("direct_manager") or r.get("reporting_manager") or "")))

        # L2 Manager
        l2_name = l2_email = ""
        if l1_id and l1_id in id_to_row:
            l2_id = _get_manager_id(id_to_row[l1_id])
            if l2_id:
                l2_name  = id_to_name.get(l2_id, "")
                l2_email = id_to_email.get(l2_id, "")

        # HRBP
        hrbp_id    = _parse_emp_id(str(r.get("hrbp_role") or ""))
        hrbp_email = id_to_email.get(hrbp_id, "")
        hrbp_name  = _parse_name(str(r.get("hrbp_role") or ""))

        # CTC fields
        ctc      = ctc_map.get(emp_id, {})
        total_ctc = _find(ctc, "ctc_total", "total_ctc", "annual_ctc", "ctc_ctc_total", "gross_ctc")
        fixed_ctc = _find(ctc, "fixed_ctc", "ctc_fixed_ctc", "fixed", "Fixed CTC")
        var_pay   = _find(ctc, "variable_pay", "ctc_variable_pay", "variable", "Variable Pay")

        # CTC breakup for severance calculations
        pf       = _find(ctc, "ctc_break_up.Provident Fund", "ctc_break_up.PF Employer",
                         "ctc_break_up.EPF Employer", "ctc_break_up.PF")
        gratuity = _find(ctc, "ctc_break_up.Gratuity")
        medical  = _find(ctc, "ctc_break_up.Mediclaim", "ctc_break_up.Medical Insurance",
                         "ctc_break_up.Group Medical Insurance")

        monthly_gross = (total_ctc - gratuity - pf - medical) / 12 if total_ctc > 0 else 0

        # DOJ: use group_doj, fall back to doj
        group_doj = str(r.get("group_date_of_joining") or r.get("date_of_joining") or "").strip()
        doj       = str(r.get("date_of_joining") or "").strip()

        employees.append({
            "employee_id":          emp_id,
            "emp_code":             emp_id,
            "full_name":            str(r.get("employee_full_name") or r.get("full_name") or r.get("name") or "").strip(),
            "company_email_id":     str(r.get("company_email_id") or r.get("email") or "").lower().strip(),
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
            "external_designation": str(r.get("designation") or "").split("(")[0].strip(),
            "internal_designation": str(r.get("job_level") or r.get("designation") or "").strip(),
            "l1_manager":           l1_name,
            "l1_manager_email":     l1_email,
            "l2_manager":           l2_name,
            "l2_manager_email":     l2_email,
            "hrbp_name":            hrbp_name,
            "hrbp_mail_id":         hrbp_email,
            "doj":                  doj,
            "group_doj":            group_doj,
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

    print(f"Built {len(employees)} employee records")
    return employees


def test_connection() -> dict:
    """Diagnostic — returns API response structure without full processing."""
    api_key     = os.getenv("DARWINBOX_MASTER_API_KEY", "")
    dataset_key = os.getenv("DARWINBOX_DATASET_KEY", "")
    try:
        resp = requests.post(
            MASTER_URL,
            json={"api_key": api_key, "datasetKey": dataset_key},
            headers=_headers(),
            timeout=30,
        )
        info = {"http_status": resp.status_code}
        j    = resp.json()
        info["response_type"] = type(j).__name__
        if isinstance(j, dict):
            info["top_level_keys"] = list(j.keys())
        raw = _extract_list(j)
        if raw:
            flat = _flatten(raw[0])
            info["total_records"]     = len(raw)
            info["first_record_keys"] = list(flat.keys())[:20]
            info["ctc_fields"]        = [k for k in flat.keys() if "ctc" in k.lower()][:10]
        else:
            info["warning"] = "No records found in response"
        return info
    except Exception as e:
        return {"error": str(e)}
