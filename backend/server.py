import base64
import json
import mimetypes
import re
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psycopg2
import psycopg2.extras

import darwinbox
from config import get_config
from constants import (
    ACTION_CASE_CLOSED,
    ACTION_CASE_CREATED,
    ACTION_CASE_REOPENED,
    ACTION_CASE_SENT_BACK,
    ACTION_CASE_UPDATED,
    ACTION_CLOSURE_EMAIL_SENT,
    ACTION_EMPLOYEE_SYNC,
    ACTION_EMPLOYEE_SYNC_FAILED,
    ACTION_SYNC_CHECK,
    ACTION_USER_ROLE_ADDED,
    ADMIN_ACTION_REOPEN,
    ADMIN_ACTION_SEND_CLOSURE_EMAIL,
    CASE_STATUS_ADMIN_CLOSED,
    CASE_STATUS_CLOSED,
    CASE_STATUS_HOLD,
    CASE_STATUS_PENDING,
    CASE_STATUS_SENT_BACK,
    CASE_STATUS_SUBMITTED,
    COMMUNICATION_COMPLETED,
    COMMUNICATION_HOLD,
    COMMUNICATION_PENDING,
    CTC_HIGH_THRESHOLD,
    DATE_FORMATS,
    DEFAULT_ROLE,
    EMAIL_STATUS_SENT,
    MAX_UPLOAD_SIZE_BYTES,
    NOTICE_PERIOD_DAYS,
    NOTICE_TYPE_SERVING_NOTICE,
    REASON_BUSINESS_CONDITIONS,
    REASON_PERFORMANCE_ISSUES,
    REFERENCE_CATALOG,
    ROLE_MANAGER,
    SYSTEM_CASE_ID,
    VARIABLE_PAY_START_DATE,
)
from models import (
    EMPLOYEE_COLUMNS,
    EMPLOYEE_FIELDS,
    ApprovalUpload,
    AuditLog,
    Employee,
    OptionValue,
    SeparationReason,
    SeparationSubReason,
    TransitionCase,
    UserRole,
    serialize_model,
    serialize_models,
)


CONFIG = get_config()
ROOT = CONFIG.backend_root
UPLOAD_ROOT = CONFIG.upload_root

def db():
    return psycopg2.connect(CONFIG.database_url)


def init_database():
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute((ROOT / "schema.sql").read_text())
            ensure_reference_catalog(cur)


def ensure_reference_catalog(cur):
    for sort_order, (reason, sub_reasons) in enumerate(REFERENCE_CATALOG["separation_reasons"].items(), start=1):
        cur.execute(
            """
            INSERT INTO separation_reasons (name, sort_order, active)
            VALUES (%s, %s, true)
            ON CONFLICT (name) DO UPDATE
              SET sort_order = EXCLUDED.sort_order
            RETURNING id
            """,
            (reason, sort_order),
        )
        reason_id = cur.fetchone()[0]
        for sub_order, sub_reason in enumerate(sub_reasons, start=1):
            cur.execute(
                """
                INSERT INTO separation_sub_reasons (reason_id, name, sort_order, active)
                VALUES (%s, %s, %s, true)
                ON CONFLICT (reason_id, name) DO UPDATE
                  SET sort_order = EXCLUDED.sort_order
                """,
                (reason_id, sub_reason, sub_order),
            )

    for group, values in REFERENCE_CATALOG["option_values"].items():
        for sort_order, value in enumerate(values, start=1):
            cur.execute(
                """
                INSERT INTO option_values (option_group, value, sort_order, active)
                VALUES (%s, %s, %s, true)
                ON CONFLICT (option_group, value) DO UPDATE
                  SET sort_order = EXCLUDED.sort_order
                """,
                (group, value, sort_order),
            )


def row_to_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def decode_jwt_payload(token):
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("Invalid bearer token")
    padding = "=" * (-len(parts[1]) % 4)
    payload = base64.urlsafe_b64decode(parts[1] + padding)
    claims = json.loads(payload.decode("utf-8"))
    exp = claims.get("exp")
    if exp is not None and float(exp) < time.time():
        raise ValueError("Bearer token has expired")
    return claims


def string_claim(claims, *keys):
    for key in keys:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def user_from_claims(claims):
    email = string_claim(claims, "email", "preferred_username", "upn", "unique_name")
    subject = string_claim(claims, "sub", "user_id", "uid", "id") or email
    first_name = string_claim(claims, "given_name", "first_name")
    last_name = string_claim(claims, "family_name", "last_name")
    name = string_claim(claims, "name", "full_name", "display_name") or " ".join(
        part for part in (first_name, last_name) if part
    )
    if not (subject or email):
        raise ValueError("Bearer token is missing user identity")
    return {
        "subject": subject,
        "email": email,
        "name": name or email,
        "claims": claims,
    }


def local_dev_token(email):
    header = {"alg": "none", "typ": "JWT"}
    now = int(time.time())
    claims = {
        "sub": email,
        "email": email,
        "name": "Vivek Kumar Naiwal" if email == CONFIG.dev_auth_email else email.split("@")[0],
        "roles": [DEFAULT_ROLE],
        "iat": now,
        "exp": now + 8 * 60 * 60,
    }

    def encode(value):
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{encode(header)}.{encode(claims)}."


def get_user_role(user_email):
    with db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT role FROM user_roles WHERE lower(email) = lower(%s) AND active = true",
                (user_email,),
            )
            role = cur.fetchone()
            if role:
                return role["role"]
            cur.execute(
                """
                SELECT employee_id FROM employees
                WHERE lower(l1_manager_email) = lower(%s)
                LIMIT 1
                """,
                (user_email,),
            )
            return ROLE_MANAGER if cur.fetchone() else None


def parse_date(value):
    if not value:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def month_delta(start, end):
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day < start.day:
        months -= 1
    return max(0, months)


def inclusive_days(start, end):
    if not start or not end or end < start:
        return 0
    return (end - start).days + 1


def money(value):
    try:
        return float(str(value or 0).replace(",", ""))
    except ValueError:
        return 0.0


def calculate_case(employee, payload):
    group_doj = parse_date(employee.get("group_doj")) or parse_date(employee.get("doj"))
    lwd = parse_date(payload.get("last_working_date"))
    dor = parse_date(payload.get("date_of_resignation"))
    reason = payload.get("separation_reason") or ""
    notice_type = payload.get("immediate_exit_or_serving_notice") or ""

    total_ctc = money(employee.get("total_ctc"))
    variable = money(employee.get("variable"))
    pf = money(employee.get("provident_fund"))
    gratuity = money(employee.get("gratuity"))
    medical = money(employee.get("medical_insurance"))
    monthly_fixed_gross = round((total_ctc - gratuity - pf - medical) / 12, 2)

    tenure = ""
    tenure_served = ""
    tenure_cohort = ""
    if group_doj and lwd and lwd >= group_doj:
        months = month_delta(group_doj, lwd)
        years = months // 12
        rem_months = months % 12
        anchor_month = group_doj.month + months
        anchor_year = group_doj.year + (anchor_month - 1) // 12
        anchor_month = ((anchor_month - 1) % 12) + 1
        anchor_day = min(group_doj.day, 28)
        anchor = date(anchor_year, anchor_month, anchor_day)
        days = max(0, (lwd - anchor).days)
        tenure = f"{years} years, {rem_months} months, {days} days"
        tenure_served = years + (1 if rem_months >= 6 else 0)
        tenure_cohort = "0-3" if years < 3 else "3+"

    ctc_cohort = "<25 lacs" if total_ctc <= CTC_HIGH_THRESHOLD else ">25 lacs"
    severance_applicability = "Yes" if reason == REASON_BUSINESS_CONDITIONS else "-"
    severance_days = 0
    if severance_applicability == "Yes":
        if ctc_cohort == ">25 lacs":
            severance_days = 60 if tenure_cohort == "3+" else 30
        else:
            severance_days = max(30, min(90, int(tenure_served or 0) * 15))

    notice_period_days = 0
    if notice_type == NOTICE_TYPE_SERVING_NOTICE and dor and lwd:
        notice_period_days = max(0, NOTICE_PERIOD_DAYS - inclusive_days(dor, lwd))

    variable_start = VARIABLE_PAY_START_DATE if group_doj and group_doj <= VARIABLE_PAY_START_DATE else group_doj
    variable_days = inclusive_days(variable_start, lwd) if severance_applicability == "Yes" else 0

    return {
        "rehire_status": "No" if reason == REASON_PERFORMANCE_ISSUES else "Yes" if reason else "",
        "tenure": tenure,
        "tenure_served": str(tenure_served) if tenure_served != "" else "",
        "tenure_cohort": tenure_cohort,
        "ctc_cohort": ctc_cohort,
        "monthly_fixed_gross": monthly_fixed_gross,
        "variable_pay_amount": round((variable / 365) * variable_days, 2) if severance_applicability == "Yes" else 0,
        "variable_days_prorata": variable_days,
        "notice_period_days": notice_period_days,
        "notice_period_amount": round((monthly_fixed_gross / 30) * notice_period_days, 2),
        "severance_applicability": severance_applicability,
        "severance_days": severance_days,
        "severance_pay_amount": round((monthly_fixed_gross / 30) * severance_days, 2),
        "april_fy_2025": "01 Apr 2025" if group_doj and group_doj <= VARIABLE_PAY_START_DATE else "",
        "one_april_2025": "01 Apr 2025" if group_doj and group_doj <= VARIABLE_PAY_START_DATE else "",
    }


def get_employee_by_code(cur, emp_code):
    cur.execute("SELECT * FROM employees WHERE emp_code = %s LIMIT 1", (emp_code,))
    return cur.fetchone()


def next_case_id(cur, emp_code):
    cur.execute("SELECT count(*) AS total FROM cases WHERE emp_code = %s", (emp_code,))
    total = cur.fetchone()["total"] or 0
    return f"C24-{emp_code}-{int(total) + 1:04d}"


def elapsed_ms(start):
    return max(1, int(round((time.perf_counter() - start) * 1000)))


def parse_iso_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def minutes_since(value):
    timestamp = parse_iso_datetime(value)
    if not timestamp:
        return None
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() // 60))


def next_sync_label(last_synced_at):
    timestamp = parse_iso_datetime(last_synced_at)
    if not timestamp:
        return "not scheduled"
    if not timestamp.tzinfo:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    elapsed = int((datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds() // 60)
    remaining = max(0, 60 - elapsed)
    return "due now" if remaining == 0 else f"in {remaining} min"


def upsert_employees(cur, employees):
    if not employees:
        return 0
    columns = EMPLOYEE_COLUMNS + ["synced_at"]
    update_columns = [column for column in columns if column != "employee_id"]
    assignments = ", ".join([f"{column} = EXCLUDED.{column}" for column in update_columns])
    placeholders = ", ".join(["%s"] * len(columns))
    total = 0
    for index in range(0, len(employees), 200):
        batch = employees[index:index + 200]
        values = [
            [employee.get(column) if column != "synced_at" else datetime.now(timezone.utc) for column in columns]
            for employee in batch
        ]
        psycopg2.extras.execute_batch(
            cur,
            f"""
            INSERT INTO employees ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (employee_id) DO UPDATE SET {assignments}
            """,
            values,
            page_size=200,
        )
        total += len(batch)
    return total


class ApiHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", CONFIG.frontend_origin)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PATCH,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Transition-User")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def do_PATCH(self):
        self.route()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, data, status=200):
        body = json.dumps(data, default=row_to_json).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def current_user(self, optional=False):
        auth_header = self.headers.get("Authorization", "").strip()
        if auth_header.lower().startswith("bearer "):
            try:
                user = user_from_claims(decode_jwt_payload(auth_header.split(" ", 1)[1].strip()))
            except ValueError as exc:
                raise PermissionError(str(exc)) from exc
            user["role"] = get_user_role(user.get("email", "")) or DEFAULT_ROLE
            return user

        if optional:
            return None

        if CONFIG.dev_auth_enabled:
            email = self.headers.get("X-Transition-User", CONFIG.dev_auth_email).strip() or CONFIG.dev_auth_email
            return {
                "subject": email,
                "email": email,
                "name": "Vivek Kumar Naiwal" if email == CONFIG.dev_auth_email else email.split("@")[0],
                "role": get_user_role(email) or DEFAULT_ROLE,
                "claims": {"authType": "local_dev"},
            }

        raise PermissionError("Authentication required")

    def route(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        try:
            if path == "/api/health":
                return self.send_json({"ok": True, "database": "postgres"})
            if path == "/api/auth/config":
                return self.auth_config()
            if path == "/api/auth/dev-login" and self.command == "POST":
                return self.dev_login()
            if path == "/api/auth/me" and self.command == "GET":
                user = self.current_user()
                return self.send_json({"user": self.public_user(user)})
            if path == "/api/public/summary" and self.command == "GET":
                return self.public_summary()
            if path == "/api/options" and self.command == "GET":
                self.current_user()
                return self.send_json(self.options())
            if path == "/api/bootstrap":
                return self.bootstrap(params)
            if path == "/api/calculate" and self.command == "POST":
                return self.calculate()
            if path == "/api/uploads" and self.command == "POST":
                return self.upload_file()
            if re.match(r"^/api/uploads/[^/]+$", path) and self.command == "GET":
                upload_id = path.rsplit("/", 1)[1]
                return self.serve_upload(upload_id)
            if path == "/api/employees":
                return self.employees(params)
            if re.match(r"^/api/employees/[^/]+$", path) and self.command == "GET":
                emp_code = path.rsplit("/", 1)[1]
                return self.employee_detail(emp_code)
            if path == "/api/cases" and self.command == "GET":
                return self.cases(params)
            if path == "/api/cases" and self.command == "POST":
                return self.create_case()
            if re.match(r"^/api/cases/[^/]+$", path):
                case_id = path.rsplit("/", 1)[1]
                if self.command == "GET":
                    return self.case_detail(case_id)
                if self.command == "PATCH":
                    return self.update_case(case_id)
            if path == "/api/roles" and self.command == "GET":
                return self.roles()
            if path == "/api/roles" and self.command == "POST":
                return self.add_role()
            if re.match(r"^/api/roles/[^/]+$", path) and self.command == "PATCH":
                role_id = path.rsplit("/", 1)[1]
                return self.update_role(role_id)
            if path == "/api/sync/test" and self.command == "POST":
                return self.sync_test()
            if path == "/api/sync/check" and self.command == "POST":
                return self.record_sync_check()
            if path == "/api/sync" and self.command == "POST":
                return self.sync()
            return self.send_json({"error": "Not found"}, 404)
        except PermissionError as exc:
            return self.send_json({"error": str(exc)}, 401)
        except psycopg2.Error as exc:
            return self.send_json({"error": "Database error", "detail": str(exc)}, 500)
        except Exception as exc:
            return self.send_json({"error": str(exc)}, 500)

    def public_user(self, user):
        return {
            "email": user.get("email", ""),
            "name": user.get("name") or user.get("email", ""),
            "role": user.get("role", DEFAULT_ROLE),
            "subject": user.get("subject", ""),
        }

    def auth_config(self):
        return self.send_json({
            "authApiUrl": CONFIG.bifrost.auth_api_url,
            "clientId": CONFIG.bifrost.client_id,
            "redirectUri": CONFIG.bifrost.redirect_uri,
            "userServiceUrl": CONFIG.bifrost.user_service_url,
            "devAuthEnabled": CONFIG.dev_auth_enabled,
            "defaultEmail": CONFIG.dev_auth_email,
        })

    def public_summary(self):
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                return self.send_json({"metrics": self.metrics(cur)})

    def options(self, cur=None):
        if cur is None:
            with db() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as fresh_cur:
                    return self.options(fresh_cur)

        cur.execute(
            """
            SELECT * FROM separation_reasons
            WHERE active = true
            ORDER BY sort_order, name
            """
        )
        reasons = serialize_models(SeparationReason, cur.fetchall())
        reason_names = [row["name"] for row in reasons]
        sub_reasons = {name: [] for name in reason_names}
        if reasons:
            cur.execute(
                """
                SELECT s.*, r.name AS reason_name
                FROM separation_sub_reasons s
                JOIN separation_reasons r ON r.id = s.reason_id
                WHERE r.active = true AND s.active = true
                ORDER BY r.sort_order, r.name, s.sort_order, s.name
                """
            )
            for raw_row in cur.fetchall():
                row = serialize_model(SeparationSubReason, raw_row)
                sub_reasons.setdefault(raw_row["reason_name"], []).append(row["name"])

        cur.execute(
            """
            SELECT * FROM option_values
            WHERE active = true
            ORDER BY option_group, sort_order, value
            """
        )
        grouped = {}
        for row in serialize_models(OptionValue, cur.fetchall()):
            grouped.setdefault(row["option_group"], []).append(row["value"])

        return {
            "separation_reasons": reason_names,
            "separation_sub_reasons": sub_reasons,
            "notice_types": grouped.get("notice_type", []),
            "garden_leave": grouped.get("garden_leave", []),
            "communication_statuses": grouped.get("communication_status", []),
            "roles": grouped.get("role", []),
            "defaults": {
                "noticeType": (grouped.get("notice_type") or [""])[0],
                "gardenLeave": (grouped.get("garden_leave") or [""])[0],
            },
        }

    def dev_login(self):
        if not CONFIG.dev_auth_enabled:
            return self.send_json({"error": "Local dev login is disabled"}, 403)
        payload = self.read_json()
        email = (payload.get("email") or CONFIG.dev_auth_email).strip().lower()
        if not email.endswith("@cars24.com"):
            return self.send_json({"error": "Only @cars24.com emails allowed"}, 400)
        token = local_dev_token(email)
        role = get_user_role(email) or DEFAULT_ROLE
        return self.send_json({
            "access_token": token,
            "refresh_token": token,
            "session_id": f"local-{email}",
            "user": {
                "email": email,
                "name": "Vivek Kumar Naiwal" if email == CONFIG.dev_auth_email else email.split("@")[0],
                "role": role,
                "subject": email,
            },
        })

    def bootstrap(self, params):
        user = self.current_user()
        email = user["email"]
        role = user.get("role") or get_user_role(email) or DEFAULT_ROLE
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                data = {
                    "user": self.public_user({**user, "role": role}),
                    "role": role,
                    "employees": self.employee_rows(cur, email),
                    "cases": self.case_rows(cur, None, None),
                    "roles": self.role_rows(cur),
                    "sync": self.sync_status(cur),
                    "metrics": self.metrics(cur),
                    "options": self.options(cur),
                }
        return self.send_json(data)

    def employee_rows(self, cur, user):
        cur.execute(
            """
            SELECT * FROM employees
            WHERE employee_status = 'Active'
              AND (
                lower(l1_manager_email) = lower(%s)
                OR emp_code IN (
                  SELECT emp_code FROM manager_overrides
                  WHERE lower(manager_email) = lower(%s)
                )
              )
            ORDER BY full_name
            """,
            (user, user),
        )
        return serialize_models(Employee, cur.fetchall())

    def employees(self, params):
        user = self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                return self.send_json(self.employee_rows(cur, user["email"]))

    def employee_detail(self, emp_code):
        self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                employee = get_employee_by_code(cur, emp_code)
                if not employee:
                    return self.send_json({"error": "Employee not found"}, 404)
                return self.send_json(serialize_model(Employee, employee))

    def case_rows(self, cur, scope, user, q=""):
        query = "SELECT * FROM cases"
        values = []
        filters = []
        if scope == "my" and user:
            filters.append("lower(created_by) = lower(%s)")
            values.append(user)
        if q:
            filters.append("(case_id ILIKE %s OR emp_name ILIKE %s OR emp_code ILIKE %s)")
            values.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY created_at DESC"
        cur.execute(query, values)
        return serialize_models(TransitionCase, cur.fetchall())

    def cases(self, params):
        user = self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                return self.send_json(self.case_rows(
                    cur,
                    params.get("scope"),
                    user["email"] if params.get("scope") == "my" else None,
                    params.get("q", ""),
                ))

    def calculate(self):
        self.current_user()
        payload = self.read_json()
        emp_code = payload.get("emp_code")
        if not emp_code:
            return self.send_json({"error": "emp_code is required"}, 400)
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                employee = get_employee_by_code(cur, emp_code)
                if not employee:
                    return self.send_json({"error": "Employee not found"}, 404)
                return self.send_json(calculate_case(employee, payload))

    def case_detail(self, case_id):
        self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM cases WHERE case_id = %s", (case_id,))
                case = cur.fetchone()
                if not case:
                    return self.send_json({"error": "Case not found"}, 404)
                cur.execute(
                    "SELECT * FROM audit_log WHERE case_id = %s ORDER BY created_at DESC",
                    (case_id,),
                )
                return self.send_json({
                    "case": serialize_model(TransitionCase, case),
                    "audit": serialize_models(AuditLog, cur.fetchall()),
                })

    def create_case(self):
        user = self.current_user()
        payload = self.read_json()
        emp_code = payload.get("emp_code")
        if not emp_code:
            return self.send_json({"error": "emp_code is required"}, 400)
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                employee = get_employee_by_code(cur, emp_code)
                if not employee:
                    return self.send_json({"error": "Employee not found"}, 404)

                calc = calculate_case(employee, payload)
                communication_status = payload.get("communication_status")
                status = (
                    CASE_STATUS_SUBMITTED
                    if communication_status == COMMUNICATION_COMPLETED
                    else CASE_STATUS_HOLD
                    if communication_status == COMMUNICATION_HOLD
                    else CASE_STATUS_PENDING
                )
                data = {
                    **{key: employee.get(key) for key in EMPLOYEE_FIELDS},
                    "case_id": next_case_id(cur, emp_code),
                    "emp_name": employee.get("full_name"),
                    "official_email": employee.get("company_email_id"),
                    "personal_email": employee.get("personal_email_id"),
                    "personal_contact": employee.get("personal_mobile_no"),
                    "date_of_resignation": payload.get("date_of_resignation"),
                    "last_working_date": payload.get("last_working_date"),
                    "immediate_exit_or_serving_notice": payload.get("immediate_exit_or_serving_notice"),
                    "garden_leave": payload.get("garden_leave"),
                    "separation_reason": payload.get("separation_reason"),
                    "separation_sub_reason": payload.get("separation_sub_reason"),
                    "communication_status": payload.get("communication_status"),
                    "remarks": payload.get("remarks", ""),
                    "approval_file_url": payload.get("approval_file_url", ""),
                    "approval_file_name": payload.get("approval_file_name", ""),
                    "status": status,
                    "created_by": user["email"],
                    "created_by_role": user.get("role", DEFAULT_ROLE),
                    **calc,
                }
                columns = list(data.keys())
                placeholders = ", ".join(["%s"] * len(columns))
                cur.execute(
                    f"INSERT INTO cases ({', '.join(columns)}) VALUES ({placeholders}) RETURNING *",
                    [data[col] for col in columns],
                )
                created = cur.fetchone()
                cur.execute(
                    "INSERT INTO audit_log (action, case_id, user_email, remarks) VALUES (%s, %s, %s, %s)",
                    (ACTION_CASE_CREATED, created["case_id"], user["email"], data.get("remarks", "")),
                )
                return self.send_json(serialize_model(TransitionCase, created), 201)

    def update_case(self, case_id):
        user = self.current_user()
        payload = self.read_json()
        action = payload.get("action")
        remarks = payload.get("remarks", "")
        if action == CASE_STATUS_CLOSED:
            updates = {
                "status": CASE_STATUS_ADMIN_CLOSED,
                "closure_status": CASE_STATUS_CLOSED,
                "admin_action": CASE_STATUS_CLOSED,
                "admin_action_status": CASE_STATUS_CLOSED,
                "admin_closed_status": CASE_STATUS_CLOSED,
                "admin_closed_at": datetime.now(timezone.utc),
                "admin_closed_by": user["email"],
                "admin_remarks": remarks,
            }
            audit_action = ACTION_CASE_CLOSED
        elif action == CASE_STATUS_SENT_BACK:
            updates = {
                "status": CASE_STATUS_SENT_BACK,
                "communication_status": COMMUNICATION_PENDING,
                "sent_back_at": datetime.now(timezone.utc),
                "sent_back_by": user["email"],
                "admin_remarks": remarks,
            }
            audit_action = ACTION_CASE_SENT_BACK
        elif action == ADMIN_ACTION_REOPEN:
            updates = {
                "status": CASE_STATUS_SUBMITTED,
                "closure_status": None,
                "admin_action": None,
                "admin_action_status": None,
                "admin_closed_status": None,
                "admin_closed_at": None,
                "admin_closed_by": None,
                "email_sent": False,
                "email_sent_at": None,
                "email_sent_status": None,
                "admin_remarks": remarks,
            }
            audit_action = ACTION_CASE_REOPENED
        elif action == ADMIN_ACTION_SEND_CLOSURE_EMAIL:
            updates = {
                "email_sent": True,
                "email_sent_at": datetime.now(timezone.utc),
                "email_sent_status": EMAIL_STATUS_SENT,
                "admin_remarks": remarks,
            }
            audit_action = ACTION_CLOSURE_EMAIL_SENT
        else:
            updates = {key: value for key, value in payload.items() if key in {"remarks", "communication_status", "status"}}
            audit_action = ACTION_CASE_UPDATED

        if not updates:
            return self.send_json({"error": "No valid updates supplied"}, 400)

        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                assignments = ", ".join([f"{key} = %s" for key in updates])
                values = list(updates.values()) + [case_id]
                cur.execute(f"UPDATE cases SET {assignments} WHERE case_id = %s RETURNING *", values)
                updated = cur.fetchone()
                if not updated:
                    return self.send_json({"error": "Case not found"}, 404)
                cur.execute(
                    "INSERT INTO audit_log (action, case_id, user_email, remarks) VALUES (%s, %s, %s, %s)",
                    (audit_action, case_id, user["email"], remarks),
                )
                return self.send_json(serialize_model(TransitionCase, updated))

    def role_rows(self, cur):
        cur.execute("SELECT * FROM user_roles ORDER BY created_at DESC")
        return serialize_models(UserRole, cur.fetchall())

    def roles(self):
        self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                return self.send_json(self.role_rows(cur))

    def add_role(self):
        user = self.current_user()
        payload = self.read_json()
        email = (payload.get("email") or "").strip().lower()
        role = payload.get("role") or DEFAULT_ROLE
        if not email.endswith("@cars24.com"):
            return self.send_json({"error": "Only @cars24.com emails allowed"}, 400)
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO user_roles (email, role, active)
                    VALUES (%s, %s, true)
                    ON CONFLICT (email) DO UPDATE SET role = EXCLUDED.role, active = true
                    RETURNING *
                    """,
                    (email, role),
                )
                role_row = cur.fetchone()
                cur.execute(
                    "INSERT INTO audit_log (action, case_id, user_email, remarks) VALUES (%s, %s, %s, %s)",
                    (ACTION_USER_ROLE_ADDED, SYSTEM_CASE_ID, user["email"], f"{email} -> {role}"),
                )
                return self.send_json(serialize_model(UserRole, role_row), 201)

    def update_role(self, role_id):
        self.current_user()
        payload = self.read_json()
        active = bool(payload.get("active", False))
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("UPDATE user_roles SET active = %s WHERE id = %s RETURNING *", (active, role_id))
                role_row = cur.fetchone()
                if not role_row:
                    return self.send_json({"error": "Role not found"}, 404)
                return self.send_json(serialize_model(UserRole, role_row))

    def upload_file(self):
        user = self.current_user()
        payload = self.read_json()
        file_name = (payload.get("file_name") or "").strip()
        content_type = (payload.get("content_type") or "application/octet-stream").strip()
        raw_data = payload.get("data_base64") or ""
        if not file_name or not raw_data:
            return self.send_json({"error": "file_name and data_base64 are required"}, 400)
        if "," in raw_data:
            raw_data = raw_data.split(",", 1)[1]
        try:
            content = base64.b64decode(raw_data, validate=True)
        except Exception:
            return self.send_json({"error": "Invalid base64 file payload"}, 400)
        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            return self.send_json({"error": "File exceeds 200 MB limit"}, 400)

        UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
        upload_id = str(uuid.uuid4())
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name).name).strip("._") or "approval"
        stored_name = f"{upload_id}_{safe_name}"
        stored_path = UPLOAD_ROOT / stored_name
        stored_path.write_bytes(content)

        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO approval_uploads
                      (id, original_name, stored_name, content_type, size_bytes, uploaded_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (upload_id, file_name, stored_name, content_type, len(content), user["email"]),
                )
                row = serialize_model(ApprovalUpload, cur.fetchone())
                row["url"] = f"/api/uploads/{upload_id}"
                return self.send_json(row, 201)

    def serve_upload(self, upload_id):
        self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM approval_uploads WHERE id = %s", (upload_id,))
                row = cur.fetchone()
                if not row:
                    return self.send_json({"error": "Upload not found"}, 404)
        upload = serialize_model(ApprovalUpload, row)
        file_path = UPLOAD_ROOT / upload["stored_name"]
        if not file_path.exists():
            return self.send_json({"error": "Upload file is missing on disk"}, 404)
        content = file_path.read_bytes()
        content_type = upload["content_type"] or mimetypes.guess_type(upload["original_name"])[0] or "application/octet-stream"
        download_name = str(upload["original_name"]).replace('"', "")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Content-Disposition", f'inline; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(content)

    def sync_checks(self, cur):
        db_start = time.perf_counter()
        cur.execute("SELECT 1 AS ok")
        database_ok = cur.fetchone()["ok"] == 1
        database_ms = elapsed_ms(db_start)

        employee_start = time.perf_counter()
        cur.execute("SELECT count(*) AS total FROM employees")
        employee_count = cur.fetchone()["total"] or 0
        employee_ms = elapsed_ms(employee_start)

        payroll_start = time.perf_counter()
        cur.execute("SELECT count(*) AS total FROM employees WHERE total_ctc IS NOT NULL AND total_ctc > 0")
        payroll_rows = cur.fetchone()["total"] or 0
        payroll_ms = elapsed_ms(payroll_start)

        darwinbox_start = time.perf_counter()
        darwinbox_status = darwinbox.test_connection()
        darwinbox_ms = elapsed_ms(darwinbox_start)
        darwinbox_ok = bool(darwinbox_status.get("configured") and not darwinbox_status.get("error"))

        return {
            "ok": bool(database_ok),
            "checks": {
                "database": {"ok": bool(database_ok), "latency_ms": database_ms},
                "employee_cache": {"rows": int(employee_count), "latency_ms": employee_ms},
                "payroll_cache": {"rows": int(payroll_rows), "latency_ms": payroll_ms},
                "darwinbox": {
                    "ok": darwinbox_ok,
                    "latency_ms": darwinbox_ms,
                    **darwinbox_status,
                },
            },
        }

    def sync_test(self):
        self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                payload = self.sync_checks(cur)
                payload["metrics"] = self.metrics(cur)
                return self.send_json(payload)

    def record_sync_check(self):
        user = self.current_user()
        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                payload = self.sync_checks(cur)
                checks = payload["checks"]
                darwinbox_status = checks["darwinbox"]
                darwinbox_summary = (
                    "configured"
                    if darwinbox_status.get("configured")
                    else f"missing {', '.join(darwinbox_status.get('missing', [])) or 'credentials'}"
                )
                remarks = (
                    f"Recorded sync check: DB {checks['database']['latency_ms']}ms, "
                    f"{checks['employee_cache']['rows']} employees, "
                    f"{checks['payroll_cache']['rows']} payroll rows, "
                    f"Darwinbox {darwinbox_summary}."
                )
                cur.execute(
                    "INSERT INTO audit_log (action, case_id, user_email, remarks) VALUES (%s, %s, %s, %s)",
                    (ACTION_SYNC_CHECK, SYSTEM_CASE_ID, user["email"], remarks[:500]),
                )
                payload["sync"] = self.sync_status(cur)
                payload["metrics"] = self.metrics(cur)
                return self.send_json(payload, 201)

    def sync_status(self, cur):
        cur.execute(
            """
            SELECT created_at FROM audit_log
            WHERE action IN (%s, %s)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (ACTION_EMPLOYEE_SYNC, ACTION_SYNC_CHECK),
        )
        sync = cur.fetchone()
        cur.execute("SELECT count(*) AS total FROM employees")
        count = cur.fetchone()["total"]
        last_synced_at = sync["created_at"] if sync else None
        return {
            "last_synced_at": row_to_json(last_synced_at) if last_synced_at else None,
            "last_sync_minutes": minutes_since(last_synced_at),
            "employee_count": count,
        }

    def metrics(self, cur):
        start = time.perf_counter()
        cur.execute("SELECT count(*) AS total FROM employees")
        employee_count = cur.fetchone()["total"] or 0
        master_api_ms = elapsed_ms(start)

        start = time.perf_counter()
        cur.execute(
            """
            SELECT
              count(*) AS total,
              count(*) FILTER (WHERE total_ctc IS NOT NULL AND total_ctc > 0) AS with_ctc
            FROM employees
            """
        )
        ctc = cur.fetchone()
        payroll_api_ms = elapsed_ms(start)
        ctc_total = ctc["total"] or 0
        ctc_ready = ctc["with_ctc"] or 0

        cur.execute(
            """
            SELECT
              count(*) AS total,
              count(*) FILTER (
                WHERE coalesce(closure_status, '') <> %s
                  AND coalesce(status, '') <> %s
              ) AS open_total
            FROM cases
            """,
            (CASE_STATUS_CLOSED, CASE_STATUS_ADMIN_CLOSED),
        )
        case_counts = cur.fetchone()

        cur.execute(
            """
            SELECT count(*) AS total FROM audit_log
            WHERE action = %s
              AND created_at >= now() - interval '24 hours'
            """,
            (ACTION_EMPLOYEE_SYNC_FAILED,),
        )
        failed_syncs = cur.fetchone()["total"] or 0

        sync = self.sync_status(cur)
        next_auto_sync = next_sync_label(sync.get("last_synced_at"))
        cache_hit_rate = 0 if ctc_total == 0 else round((ctc_ready / ctc_total) * 100, 1)
        return {
            "employee_count": int(employee_count),
            "open_cases": int(case_counts["open_total"] or 0),
            "total_cases": int(case_counts["total"] or 0),
            "last_sync_minutes": sync.get("last_sync_minutes"),
            "active_cases": int(case_counts["open_total"] or 0),
            "pipeline": {
                "master_api": f"{master_api_ms}ms",
                "payroll_api": f"{payroll_api_ms}ms",
                "cache_hit_rate": f"{cache_hit_rate}%",
                "failed_syncs": str(failed_syncs),
                "next_auto_sync": next_auto_sync,
            },
        }

    def sync(self):
        user = self.current_user()
        started = time.perf_counter()
        try:
            employees = darwinbox.fetch_employee_master()
        except Exception as exc:
            try:
                with db() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "INSERT INTO audit_log (action, case_id, user_email, remarks) VALUES (%s, %s, %s, %s)",
                            (ACTION_EMPLOYEE_SYNC_FAILED, SYSTEM_CASE_ID, user["email"], str(exc)[:500]),
                        )
            except psycopg2.Error:
                pass
            status = 400 if "Missing Darwinbox credentials" in str(exc) else 502
            return self.send_json({"error": str(exc)}, status)

        with db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                rows_synced = upsert_employees(cur, employees)
                elapsed = elapsed_ms(started)
                cur.execute(
                    "INSERT INTO audit_log (action, case_id, user_email, remarks) VALUES (%s, %s, %s, %s)",
                    (ACTION_EMPLOYEE_SYNC, SYSTEM_CASE_ID, user["email"], f"Synced {rows_synced} rows from Darwinbox in {elapsed}ms"),
                )
                return self.send_json({
                    "rows_synced": rows_synced,
                    "elapsed_ms": elapsed,
                    "sync": self.sync_status(cur),
                    "metrics": self.metrics(cur),
                })


if __name__ == "__main__":
    init_database()
    server = ThreadingHTTPServer((CONFIG.backend_host, CONFIG.backend_port), ApiHandler)
    print(f"Backend running at http://{CONFIG.backend_host}:{CONFIG.backend_port}")
    print(f"Using Postgres: {CONFIG.database_url}")
    server.serve_forever()
