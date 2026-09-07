# Exact port of calculateCase_() from ATL Portal Code.gs (via calculations.ts)
from datetime import date, datetime
from dateutil.relativedelta import relativedelta


def _parse_date(v):
    if not v:
        return None
    s = str(v).strip()
    if not s or s in ("None", "nan"):
        return None
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%Y",
                "%Y/%m/%d", "%d %B %Y", "%B %d, %Y", "%d/%b/%Y"]:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _fmt(d):
    return d.strftime("%d %b %Y") if d else ""


def _diff_ymd(start, end):
    if not start or not end or end < start:
        return None
    rd = relativedelta(end, start)
    return {"years": max(0, rd.years), "months": max(0, rd.months), "days": max(0, rd.days)}


def _years_between(start, end):
    return max(0, relativedelta(end, start).years)


def _days_inclusive(start, end):
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def _num(v):
    try:
        return float(str(v or 0).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _r2(n):
    return round(float(n or 0), 2)


def calculate_case(employee: dict, input_data: dict) -> dict:
    # Use group_doj for all tenure/severance calculations; fall back to doj if blank
    group_doj = _parse_date(employee.get("group_doj")) or _parse_date(employee.get("doj"))
    lwd            = _parse_date(input_data.get("last_working_date"))
    dor            = _parse_date(input_data.get("date_of_resignation"))
    sep_reason     = str(input_data.get("separation_reason") or "").strip()
    exit_or_notice = str(input_data.get("immediate_exit_or_serving_notice") or "").strip()

    total_ctc = _num(employee.get("total_ctc"))
    var_ctc   = _num(employee.get("variable"))
    pf        = _num(employee.get("provident_fund"))
    gratuity  = _num(employee.get("gratuity"))
    medical   = _num(employee.get("medical_insurance"))

    today      = date.today()
    apr1_2025  = date(2025, 4, 1)
    sep30_2024 = date(2024, 9, 30)

    monthly_fixed_gross = _r2((total_ctc - gratuity - pf - medical) / 12)

    rehire_status = ""
    if sep_reason:
        rehire_status = "No" if sep_reason == "Performance Issues" else "Yes"

    tenure = ""
    if group_doj and lwd and lwd >= group_doj:
        d = _diff_ymd(group_doj, lwd)
        if d:
            tenure = f"{d['years']} years, {d['months']} months, {d['days']} days"

    tenure_cohort = ""
    if group_doj:
        if group_doj > today:
            tenure_cohort = "Future"
        elif _years_between(group_doj, today) < 3:
            tenure_cohort = "0-3"
        else:
            tenure_cohort = "3+"

    tenure_served = ""
    if group_doj and lwd and lwd >= group_doj:
        d = _diff_ymd(group_doj, lwd)
        if d:
            tenure_served = d["years"] + (1 if d["months"] >= 6 else 0)

    severance_applicability = "Yes" if sep_reason == "Business Conditions" else "-"
    ctc_cohort = "<25 lacs" if total_ctc <= 2500000 else ">25 lacs"

    one_april_2025 = ""
    april_fy_2025  = ""
    apr1_used      = None
    if group_doj and group_doj <= sep30_2024:
        one_april_2025 = _fmt(apr1_2025)
        april_fy_2025  = _fmt(apr1_2025)
        apr1_used      = apr1_2025

    variable_days_prorata = 0
    if severance_applicability == "Yes" and lwd:
        if apr1_used:
            variable_days_prorata = _days_inclusive(apr1_used, lwd)
        elif group_doj:
            variable_days_prorata = _days_inclusive(group_doj, lwd)

    severance_days = 0
    if severance_applicability == "Yes":
        if ctc_cohort == ">25 lacs" and tenure_cohort == "3+":
            severance_days = 60
        elif ctc_cohort == ">25 lacs" and tenure_cohort == "0-3":
            severance_days = 30
        else:
            base = int(tenure_served or 0) * 15
            severance_days = max(30, min(90, base))

    notice_period_days = 0
    if exit_or_notice == "Serving Notice" and dor and lwd:
        served = _days_inclusive(dor, lwd)
        notice_period_days = max(0, 30 - served)

    notice_period_amount = _r2((monthly_fixed_gross / 30) * notice_period_days)
    severance_pay_amount = _r2((monthly_fixed_gross / 30) * severance_days)
    variable_pay_amount  = _r2((var_ctc / 365) * variable_days_prorata) if severance_applicability == "Yes" else 0.0

    return {
        "rehire_status":           rehire_status,
        "tenure":                  tenure,
        "tenure_cohort":           tenure_cohort,
        "tenure_served":           tenure_served,
        "ctc_cohort":              ctc_cohort,
        "monthly_fixed_gross":     monthly_fixed_gross,
        "severance_applicability": severance_applicability,
        "severance_days":          severance_days,
        "notice_period_days":      notice_period_days,
        "variable_days_prorata":   variable_days_prorata,
        "notice_period_amount":    notice_period_amount,
        "severance_pay_amount":    severance_pay_amount,
        "variable_pay_amount":     variable_pay_amount,
        "april_fy_2025":           april_fy_2025,
        "one_april_2025":          one_april_2025,
    }
