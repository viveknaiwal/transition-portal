from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from constants import EMPLOYEE_COLUMNS, EMPLOYEE_FIELDS, ROLE_OPTIONS
from crypto import blind_index, decrypt_value, encrypt_value, is_encrypted_value


def json_value(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class DbModel:
    table_name: ClassVar[str] = ""
    primary_key: ClassVar[str] = "id"
    encrypted_fields: ClassVar[set[str]] = set()
    blind_index_fields: ClassVar[dict[str, str]] = {}

    @classmethod
    def model_fields(cls):
        return [field.name for field in fields(cls)]

    @classmethod
    def from_row(cls, row):
        row_data = dict(row or {})
        for name in cls.encrypted_fields:
            if name in row_data:
                row_data[name] = decrypt_value(row_data.get(name))
        return cls(**{name: row_data.get(name) for name in cls.model_fields() if name in row_data})

    def to_dict(self):
        return {name: json_value(getattr(self, name)) for name in self.model_fields()}

    def to_record(self, columns=None, include_none=True):
        source = self.to_dict()
        selected = list(columns or source.keys())
        record = {
            key: source.get(key)
            for key in selected
            if include_none or source.get(key) is not None
        }
        for key in list(record):
            if key in self.encrypted_fields:
                record[key] = encrypt_value(record[key])
        for source_field, index_field in self.blind_index_fields.items():
            if source_field in source and source.get(source_field) not in {None, ""}:
                record[index_field] = blind_index(source.get(source_field))
            elif source_field in selected or index_field in selected:
                record[index_field] = None
        return record


@dataclass(frozen=True)
class UserRole(DbModel):
    table_name: ClassVar[str] = "user_roles"
    encrypted_fields: ClassVar[set[str]] = {"email"}
    blind_index_fields: ClassVar[dict[str, str]] = {"email": "email_blind_idx"}

    id: Any = None
    email: Any = None
    role: Any = None
    active: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class Employee(DbModel):
    table_name: ClassVar[str] = "employees"
    primary_key: ClassVar[str] = "employee_id"
    encrypted_fields: ClassVar[set[str]] = {
        "full_name", "company_email_id", "personal_email_id", "personal_mobile_no",
        "entity", "business_unit", "lob", "function", "sub_function", "region", "site_name",
        "grade", "band", "external_designation", "internal_designation", "l1_manager",
        "l1_manager_email", "l2_manager", "l2_manager_email", "hrbp_name", "hrbp_mail_id",
        "doj", "group_doj", "gender", "fixed_ctc", "variable", "pli", "retention",
        "total_ctc", "monthly_gross", "provident_fund", "gratuity", "medical_insurance",
        "email_check",
    }
    blind_index_fields: ClassVar[dict[str, str]] = {
        "full_name": "full_name_blind_idx",
        "company_email_id": "company_email_id_blind_idx",
        "personal_email_id": "personal_email_id_blind_idx",
        "personal_mobile_no": "personal_mobile_no_blind_idx",
        "l1_manager_email": "l1_manager_email_blind_idx",
        "l2_manager_email": "l2_manager_email_blind_idx",
        "hrbp_mail_id": "hrbp_mail_id_blind_idx",
    }

    employee_id: Any = None
    emp_code: Any = None
    full_name: Any = None
    company_email_id: Any = None
    personal_email_id: Any = None
    personal_mobile_no: Any = None
    entity: Any = None
    business_unit: Any = None
    lob: Any = None
    function: Any = None
    sub_function: Any = None
    region: Any = None
    site_name: Any = None
    grade: Any = None
    band: Any = None
    external_designation: Any = None
    internal_designation: Any = None
    l1_manager: Any = None
    l1_manager_email: Any = None
    l2_manager: Any = None
    l2_manager_email: Any = None
    hrbp_name: Any = None
    hrbp_mail_id: Any = None
    doj: Any = None
    group_doj: Any = None
    employee_status: Any = None
    gender: Any = None
    fixed_ctc: Any = None
    variable: Any = None
    pli: Any = None
    retention: Any = None
    total_ctc: Any = None
    monthly_gross: Any = None
    provident_fund: Any = None
    gratuity: Any = None
    medical_insurance: Any = None
    email_check: Any = None
    synced_at: Any = None


@dataclass(frozen=True)
class ManagerOverride(DbModel):
    table_name: ClassVar[str] = "manager_overrides"
    encrypted_fields: ClassVar[set[str]] = {"manager_email", "added_by", "notes"}
    blind_index_fields: ClassVar[dict[str, str]] = {"manager_email": "manager_email_blind_idx"}

    id: Any = None
    emp_code: Any = None
    manager_email: Any = None
    added_by: Any = None
    notes: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class SeparationReason(DbModel):
    table_name: ClassVar[str] = "separation_reasons"

    id: Any = None
    name: Any = None
    active: Any = None
    sort_order: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class SeparationSubReason(DbModel):
    table_name: ClassVar[str] = "separation_sub_reasons"

    id: Any = None
    reason_id: Any = None
    name: Any = None
    active: Any = None
    sort_order: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class OptionValue(DbModel):
    table_name: ClassVar[str] = "option_values"

    id: Any = None
    option_group: Any = None
    value: Any = None
    active: Any = None
    sort_order: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class TransitionCase(DbModel):
    table_name: ClassVar[str] = "cases"
    encrypted_fields: ClassVar[set[str]] = {
        "emp_name", "official_email", "personal_email", "personal_contact", "entity",
        "business_unit", "lob", "function", "sub_function", "region", "site_name", "grade",
        "band", "external_designation", "internal_designation", "l1_manager", "l1_manager_email",
        "l2_manager", "l2_manager_email", "hrbp_name", "hrbp_mail_id", "doj", "group_doj",
        "employee_status", "fixed_ctc", "variable", "pli", "retention", "total_ctc",
        "monthly_gross", "provident_fund", "gratuity", "medical_insurance", "gender",
        "date_of_resignation", "last_working_date", "immediate_exit_or_serving_notice",
        "garden_leave", "separation_reason", "separation_sub_reason", "communication_status",
        "remarks", "approval_file_url", "approval_file_name", "rehire_status", "tenure",
        "tenure_served", "tenure_cohort", "ctc_cohort", "monthly_fixed_gross",
        "variable_pay_amount", "variable_days_prorata", "notice_period_days",
        "notice_period_amount", "severance_applicability", "severance_days",
        "severance_pay_amount", "april_fy_2025", "one_april_2025", "admin_action",
        "admin_action_status", "admin_closed_status", "admin_closed_by", "sent_back_by",
        "admin_remarks", "email_sent_status", "created_by", "created_by_role",
    }
    blind_index_fields: ClassVar[dict[str, str]] = {
        "emp_name": "emp_name_blind_idx",
        "official_email": "official_email_blind_idx",
        "personal_email": "personal_email_blind_idx",
        "personal_contact": "personal_contact_blind_idx",
        "l1_manager_email": "l1_manager_email_blind_idx",
        "l2_manager_email": "l2_manager_email_blind_idx",
        "hrbp_mail_id": "hrbp_mail_id_blind_idx",
        "created_by": "created_by_blind_idx",
        "admin_closed_by": "admin_closed_by_blind_idx",
        "sent_back_by": "sent_back_by_blind_idx",
    }

    id: Any = None
    case_id: Any = None
    emp_code: Any = None
    emp_name: Any = None
    official_email: Any = None
    personal_email: Any = None
    personal_contact: Any = None
    entity: Any = None
    business_unit: Any = None
    lob: Any = None
    function: Any = None
    sub_function: Any = None
    region: Any = None
    site_name: Any = None
    grade: Any = None
    band: Any = None
    external_designation: Any = None
    internal_designation: Any = None
    l1_manager: Any = None
    l1_manager_email: Any = None
    l2_manager: Any = None
    l2_manager_email: Any = None
    hrbp_name: Any = None
    hrbp_mail_id: Any = None
    doj: Any = None
    group_doj: Any = None
    employee_status: Any = None
    fixed_ctc: Any = None
    variable: Any = None
    pli: Any = None
    retention: Any = None
    total_ctc: Any = None
    monthly_gross: Any = None
    provident_fund: Any = None
    gratuity: Any = None
    medical_insurance: Any = None
    gender: Any = None
    date_of_resignation: Any = None
    last_working_date: Any = None
    immediate_exit_or_serving_notice: Any = None
    garden_leave: Any = None
    separation_reason: Any = None
    separation_sub_reason: Any = None
    communication_status: Any = None
    remarks: Any = None
    approval_file_url: Any = None
    approval_file_name: Any = None
    rehire_status: Any = None
    tenure: Any = None
    tenure_served: Any = None
    tenure_cohort: Any = None
    ctc_cohort: Any = None
    monthly_fixed_gross: Any = None
    variable_pay_amount: Any = None
    variable_days_prorata: Any = None
    notice_period_days: Any = None
    notice_period_amount: Any = None
    severance_applicability: Any = None
    severance_days: Any = None
    severance_pay_amount: Any = None
    april_fy_2025: Any = None
    one_april_2025: Any = None
    status: Any = None
    closure_status: Any = None
    admin_action: Any = None
    admin_action_status: Any = None
    admin_closed_status: Any = None
    admin_closed_at: Any = None
    admin_closed_by: Any = None
    sent_back_at: Any = None
    sent_back_by: Any = None
    admin_remarks: Any = None
    payroll_downloaded_at: Any = None
    email_sent: Any = None
    email_sent_at: Any = None
    email_sent_status: Any = None
    created_at: Any = None
    created_by: Any = None
    created_by_role: Any = None
    updated_at: Any = None


@dataclass(frozen=True)
class AuditLog(DbModel):
    table_name: ClassVar[str] = "audit_log"
    encrypted_fields: ClassVar[set[str]] = {"user_email", "remarks"}
    blind_index_fields: ClassVar[dict[str, str]] = {"user_email": "user_email_blind_idx"}

    id: Any = None
    action: Any = None
    case_id: Any = None
    user_email: Any = None
    remarks: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class ApprovalUpload(DbModel):
    table_name: ClassVar[str] = "approval_uploads"
    encrypted_fields: ClassVar[set[str]] = {"original_name", "content_type", "uploaded_by"}
    blind_index_fields: ClassVar[dict[str, str]] = {"uploaded_by": "uploaded_by_blind_idx"}

    id: Any = None
    original_name: Any = None
    stored_name: Any = None
    content_type: Any = None
    size_bytes: Any = None
    uploaded_by: Any = None
    created_at: Any = None


TABLE_MODELS = {
    UserRole.table_name: UserRole,
    Employee.table_name: Employee,
    ManagerOverride.table_name: ManagerOverride,
    SeparationReason.table_name: SeparationReason,
    SeparationSubReason.table_name: SeparationSubReason,
    OptionValue.table_name: OptionValue,
    TransitionCase.table_name: TransitionCase,
    AuditLog.table_name: AuditLog,
    ApprovalUpload.table_name: ApprovalUpload,
}


def serialize_model(model_cls, row):
    return model_cls.from_row(row).to_dict()


def serialize_models(model_cls, rows):
    return [serialize_model(model_cls, row) for row in rows]


def encrypted_record(model_cls, data, columns=None, include_none=True):
    return model_cls(**{name: data.get(name) for name in model_cls.model_fields() if name in data}).to_record(columns, include_none)


def needs_encryption_migration(model_cls, row):
    raw = dict(row or {})
    for field_name in model_cls.encrypted_fields:
        value = raw.get(field_name)
        if value not in {None, ""} and not is_encrypted_value(value):
            return True
    for source_field, index_field in model_cls.blind_index_fields.items():
        if raw.get(source_field) not in {None, ""} and not raw.get(index_field):
            return True
    return False
