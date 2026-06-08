from datetime import date


APP_NAME = "Transition Portal"

ENV_LOCAL = "local"
ENV_DEVELOPMENT = "development"
ENV_QA = "qa"
ENV_PRODUCTION = "production"
ENV_NAMES = {ENV_LOCAL, ENV_DEVELOPMENT, ENV_QA, ENV_PRODUCTION}

DEFAULT_BACKEND_HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 5050
DEFAULT_DATABASE_URL = "dbname=transition_portal"
DEFAULT_FRONTEND_ORIGIN = "http://127.0.0.1:8501"
DEFAULT_DEV_AUTH_EMAIL = "vivek.naiwal@cars24.com"
DEFAULT_BIFROST_CLIENT_ID = "client_Q6G6tjO9NF8Ts2unKswoA"
DEFAULT_BIFROST_AUTH_API_URL = "https://auth-service-qa.qac24svc.dev"
DEFAULT_BIFROST_USER_SERVICE_URL = "https://c24-user-service-qa.qac24svc.dev"

ROLE_ADMIN = "ADMIN"
ROLE_SUB_ADMIN = "SUB_ADMIN"
ROLE_PAYROLL = "PAYROLL"
ROLE_MANAGER = "MANAGER"
ROLE_HRBP = "HRBP"
ROLE_OPTIONS = [ROLE_ADMIN, ROLE_SUB_ADMIN, ROLE_PAYROLL, ROLE_MANAGER, ROLE_HRBP]
DEFAULT_ROLE = ROLE_ADMIN

CASE_STATUS_PENDING = "Pending"
CASE_STATUS_SUBMITTED = "Submitted"
CASE_STATUS_HOLD = "Hold"
CASE_STATUS_ADMIN_CLOSED = "Admin Closed"
CASE_STATUS_SENT_BACK = "Sent Back"
CASE_STATUS_CLOSED = "Closed"
EMAIL_STATUS_SENT = "Sent"
ADMIN_ACTION_REOPEN = "Reopen"
ADMIN_ACTION_SEND_CLOSURE_EMAIL = "Send Closure Email"

COMMUNICATION_PENDING = "Pending"
COMMUNICATION_HOLD = "Hold"
COMMUNICATION_COMPLETED = "Completed"

ACTION_CASE_CREATED = "CASE_CREATED"
ACTION_CASE_CLOSED = "CASE_CLOSED"
ACTION_CASE_SENT_BACK = "CASE_SENT_BACK"
ACTION_CASE_REOPENED = "CASE_REOPENED"
ACTION_CASE_UPDATED = "CASE_UPDATED"
ACTION_CLOSURE_EMAIL_SENT = "CLOSURE_EMAIL_SENT"
ACTION_USER_ROLE_ADDED = "USER_ROLE_ADDED"
ACTION_EMPLOYEE_SYNC = "EMPLOYEE_SYNC"
ACTION_SYNC_CHECK = "SYNC_CHECK"
ACTION_EMPLOYEE_SYNC_FAILED = "EMPLOYEE_SYNC_FAILED"

SYSTEM_CASE_ID = "SYSTEM"

OPTION_GROUP_NOTICE_TYPE = "notice_type"
OPTION_GROUP_GARDEN_LEAVE = "garden_leave"
OPTION_GROUP_COMMUNICATION_STATUS = "communication_status"
OPTION_GROUP_ROLE = "role"

REASON_BUSINESS_CONDITIONS = "Business Conditions"
REASON_PERFORMANCE_ISSUES = "Performance Issues"
NOTICE_TYPE_SERVING_NOTICE = "Serving Notice"
NOTICE_TYPE_IMMEDIATE_EXIT = "Immediate Exit"

REFERENCE_CATALOG = {
    "separation_reasons": {
        REASON_BUSINESS_CONDITIONS: [
            "Role Redundancy",
            "Location Decommissioned",
            "Business Closure",
            "Cost Optimization",
        ],
        REASON_PERFORMANCE_ISSUES: [
            "PIP Unsuccessful",
            "Probation Unsuccessful",
        ],
    },
    "option_values": {
        OPTION_GROUP_NOTICE_TYPE: [NOTICE_TYPE_SERVING_NOTICE, NOTICE_TYPE_IMMEDIATE_EXIT],
        OPTION_GROUP_GARDEN_LEAVE: ["No", "Yes", "NA"],
        OPTION_GROUP_COMMUNICATION_STATUS: [
            COMMUNICATION_PENDING,
            COMMUNICATION_HOLD,
            COMMUNICATION_COMPLETED,
        ],
        OPTION_GROUP_ROLE: ROLE_OPTIONS,
    },
}

EMPLOYEE_FIELDS = [
    "emp_code",
    "entity",
    "business_unit",
    "lob",
    "function",
    "sub_function",
    "region",
    "site_name",
    "grade",
    "band",
    "external_designation",
    "internal_designation",
    "l1_manager",
    "l1_manager_email",
    "l2_manager",
    "l2_manager_email",
    "hrbp_name",
    "hrbp_mail_id",
    "doj",
    "group_doj",
    "employee_status",
    "gender",
    "fixed_ctc",
    "variable",
    "pli",
    "retention",
    "total_ctc",
    "monthly_gross",
    "provident_fund",
    "gratuity",
    "medical_insurance",
]

EMPLOYEE_COLUMNS = [
    "employee_id",
    "emp_code",
    "full_name",
    "company_email_id",
    "personal_email_id",
    "personal_mobile_no",
    *[field for field in EMPLOYEE_FIELDS if field != "emp_code"],
    "email_check",
]

PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/config",
    "/api/auth/dev-login",
    "/api/public/summary",
}

DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%b-%Y")
DARWINBOX_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%Y/%m/%d")

NOTICE_PERIOD_DAYS = 30
CTC_HIGH_THRESHOLD = 2500000
VARIABLE_PAY_START_DATE = date(2025, 4, 1)
DARWINBOX_LWD_CUTOFF = date(2026, 3, 31)
DEFAULT_DARWINBOX_BATCH_SIZE = 500
DEFAULT_DARWINBOX_CTC_FROM = "01-01-2020"

MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024

DARWINBOX_REQUIRED_KEYS = (
    "DARWINBOX_USERNAME",
    "DARWINBOX_PASSWORD",
    "DARWINBOX_MASTER_API_KEY",
    "DARWINBOX_DATASET_KEY",
)
