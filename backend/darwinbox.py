import base64
import json
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import get_config
from constants import DARWINBOX_DATE_FORMATS, DARWINBOX_LWD_CUTOFF


def _settings():
    return get_config().darwinbox


def credentials_ready():
    return _settings().configured


def missing_credentials():
    return _settings().missing_required_keys()


def _auth_header():
    config = _settings()
    raw = f"{config.username}:{config.password}"
    return "Basic " + base64.b64encode(raw.encode()).decode()


def _post_json(url, payload, timeout=120):
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": _auth_header(),
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text or "{}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Darwinbox HTTP {exc.code}: {detail[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Darwinbox connection failed: {exc.reason}") from exc


def _flatten(obj, prefix="", out=None):
    if out is None:
        out = {}
    for key, value in (obj or {}).items():
        flat_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            _flatten(value, flat_key, out)
        else:
            out[flat_key] = value
    return out


def _extract_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("employee_data", "ctc_data", "data", "employees", "result", "results", "records", "employee_details"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        values = [value for value in payload.values() if isinstance(value, dict)]
        if values:
            return values
    return []


def _get_emp_code(row):
    for key in ("employee_id", "employee_no", "emp_code", "ecode", "employeeId"):
        value = str(row.get(key, "") or "").strip()
        if value and re.match(r"^\d{4,}$", value):
            return value
    return ""


def _parse_emp_id(raw):
    match = re.search(r"\((\d+)\)", str(raw or ""))
    return match.group(1) if match else ""


def _parse_name(raw):
    return re.sub(r"\s*\(\d+\)\s*$", "", str(raw or "")).strip()


def _num(value):
    try:
        return float(str(value or 0).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value):
    text = str(value or "").strip()
    if not text or text.lower() in {"-", "na", "n/a", "null", "none", "0000-00-00"}:
        return None
    for fmt in DARWINBOX_DATE_FORMATS:
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def _should_include(row):
    status = str(row.get("employee_status", "")).strip().lower()
    exit_raw = str(row.get("date_of_exit") or row.get("date_of_leaving") or "").strip()
    if not exit_raw or exit_raw.lower() in {"-", "na", "n/a", "null", "none", "0000-00-00"}:
        return True
    exit_date = _parse_date(exit_raw)
    if exit_date is None:
        return status == "active"
    return exit_date > DARWINBOX_LWD_CUTOFF


def _clean_date_str(value):
    text = str(value or "").strip()
    normalized = text.lower().replace(".", "").replace(" ", "").replace("/", "")
    if normalized in {"", "-", "--", "na", "null", "none", "nil", "0000-00-00", "00-00-0000", "notapplicable", "notavailable"}:
        return ""
    return text


def _find(row, *keys):
    for key in keys:
        value = row.get(key)
        if value is not None:
            number = _num(value)
            if number > 0:
                return number
    return 0.0


def _get_manager_id(row):
    for field in ("reporting_manager_employee_id", "direct_manager_employee_id", "manager_employee_id", "reporting_manager_id", "direct_manager_id"):
        value = str(row.get(field, "") or "").strip()
        if value and re.match(r"^\d{4,}$", value):
            return value
    for field in ("direct_manager", "reporting_manager"):
        manager_id = _parse_emp_id(row.get(field, ""))
        if manager_id:
            return manager_id
    return ""


def fetch_ctc_data(emp_ids):
    config = _settings()
    if not config.payroll_api_key:
        return {}

    ctc_map = {}
    for index in range(0, len(emp_ids), config.batch_size):
        batch = [str(emp_id) for emp_id in emp_ids[index:index + config.batch_size]]
        _, payload = _post_json(
            config.payroll_url,
            {
                "api_key": config.payroll_api_key,
                "employee_no": batch,
                "last_modified": config.ctc_from,
                "proration_type": "monthly",
            },
            timeout=120,
        )
        for record in _extract_list(payload):
            flat = _flatten(record)
            code = _get_emp_code(flat)
            if code:
                ctc_map[code] = flat
    return ctc_map


def fetch_employee_master():
    missing = missing_credentials()
    if missing:
        raise RuntimeError(f"Missing Darwinbox credentials: {', '.join(missing)}")
    config = _settings()

    _, payload = _post_json(
        config.master_url,
        {
            "api_key": config.master_api_key,
            "datasetKey": config.dataset_key,
        },
        timeout=120,
    )
    raw_list = [_flatten(record) for record in _extract_list(payload)]
    if not raw_list:
        keys = list(payload.keys()) if isinstance(payload, dict) else []
        raise RuntimeError(f"Darwinbox master API returned no employee records. Keys: {keys}")

    filtered = [row for row in raw_list if _should_include(row)]
    id_to_email = {}
    id_to_name = {}
    id_to_row = {}
    for row in raw_list:
        employee_id = _get_emp_code(row)
        if employee_id:
            id_to_email[employee_id] = str(row.get("company_email_id") or row.get("email") or "").lower().strip()
            id_to_name[employee_id] = str(row.get("employee_full_name") or row.get("full_name") or row.get("name") or "").strip()
            id_to_row[employee_id] = row

    emp_ids = [_get_emp_code(row) for row in filtered if _get_emp_code(row)]
    ctc_map = fetch_ctc_data(emp_ids)
    employees = []
    for row in filtered:
        employee_id = _get_emp_code(row)
        if not employee_id:
            continue

        l1_id = _get_manager_id(row)
        l1_email = id_to_email.get(l1_id, "")
        l1_name = id_to_name.get(l1_id, _parse_name(row.get("direct_manager") or row.get("reporting_manager") or ""))
        l2_name = ""
        l2_email = ""
        if l1_id and l1_id in id_to_row:
            l2_id = _get_manager_id(id_to_row[l1_id])
            if l2_id:
                l2_name = id_to_name.get(l2_id, "")
                l2_email = id_to_email.get(l2_id, "")

        hrbp_id = _parse_emp_id(row.get("hrbp_role") or "")
        hrbp_email = id_to_email.get(hrbp_id, "")
        hrbp_name = _parse_name(row.get("hrbp_role") or "")
        ctc = ctc_map.get(employee_id, {})
        total_ctc = _find(ctc, "ctc_total", "total_ctc", "annual_ctc", "ctc_ctc_total", "gross_ctc")
        fixed_ctc = _find(ctc, "fixed_ctc", "ctc_fixed_ctc", "fixed", "Fixed CTC")
        variable = _find(ctc, "variable_pay", "ctc_variable_pay", "variable", "Variable Pay")
        pf = _find(ctc, "ctc_break_up.Provident Fund", "ctc_break_up.PF Employer", "ctc_break_up.EPF Employer", "ctc_break_up.PF")
        gratuity = _find(ctc, "ctc_break_up.Gratuity")
        medical = _find(ctc, "ctc_break_up.Mediclaim", "ctc_break_up.Medical Insurance", "ctc_break_up.Group Medical Insurance")
        monthly_gross = (total_ctc - gratuity - pf - medical) / 12 if total_ctc > 0 else 0
        doj = _clean_date_str(row.get("date_of_joining") or row.get("joining_date") or row.get("doj") or row.get("dateofjoining") or "")
        group_doj = _clean_date_str(row.get("group_date_of_joining") or row.get("group_doj") or row.get("group_joining_date") or "") or doj
        company_email = str(row.get("company_email_id") or row.get("email") or "").lower().strip()

        employees.append({
            "employee_id": employee_id,
            "emp_code": employee_id,
            "full_name": str(row.get("employee_full_name") or row.get("full_name") or row.get("name") or "").strip(),
            "company_email_id": company_email,
            "personal_email_id": str(row.get("personal_email_id") or "").strip(),
            "personal_mobile_no": str(row.get("personal_mobile_no") or row.get("office_mobile_no") or "").strip(),
            "entity": str(row.get("group_company") or "").strip(),
            "business_unit": str(row.get("business_unit") or "").strip(),
            "lob": str(row.get("business_lob_/_soh") or row.get("business_lob") or "").strip(),
            "function": str(row.get("top_department") or row.get("department") or "").strip(),
            "sub_function": str(row.get("sub-function") or row.get("sub_function") or "").strip(),
            "region": str(row.get("central/regional") or row.get("region") or "").strip(),
            "site_name": str(row.get("office_location") or "").strip(),
            "grade": str(row.get("job_level") or "").strip(),
            "band": str(row.get("band") or "").strip(),
            "external_designation": str(row.get("designation") or "").split("(")[0].strip(),
            "internal_designation": str(row.get("job_level") or row.get("designation") or "").strip(),
            "l1_manager": l1_name,
            "l1_manager_email": l1_email,
            "l2_manager": l2_name,
            "l2_manager_email": l2_email,
            "hrbp_name": hrbp_name,
            "hrbp_mail_id": hrbp_email,
            "doj": doj,
            "group_doj": group_doj,
            "employee_status": str(row.get("employee_status") or "").strip(),
            "gender": str(row.get("gender") or "").strip(),
            "fixed_ctc": fixed_ctc,
            "variable": variable,
            "pli": 0,
            "retention": 0,
            "total_ctc": total_ctc,
            "monthly_gross": round(monthly_gross),
            "provident_fund": pf,
            "gratuity": gratuity,
            "medical_insurance": medical,
            "email_check": company_email,
        })
    return employees


def test_connection():
    missing = missing_credentials()
    if missing:
        return {"configured": False, "missing": missing}
    config = _settings()
    try:
        status, payload = _post_json(
            config.master_url,
            {
                "api_key": config.master_api_key,
                "datasetKey": config.dataset_key,
            },
            timeout=30,
        )
        records = _extract_list(payload)
        return {
            "configured": True,
            "http_status": status,
            "record_count": len(records),
            "response_type": type(payload).__name__,
            "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else [],
        }
    except Exception as exc:
        return {"configured": True, "error": str(exc)}
