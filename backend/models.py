from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from constants import EMPLOYEE_COLUMNS, EMPLOYEE_FIELDS, ROLE_OPTIONS


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

    @classmethod
    def model_fields(cls):
        return [field.name for field in fields(cls)]

    @classmethod
    def from_row(cls, row):
        row_data = dict(row or {})
        return cls(**{name: row_data.get(name) for name in cls.model_fields() if name in row_data})

    def to_dict(self):
        return {name: json_value(getattr(self, name)) for name in self.model_fields()}

    def to_record(self, columns=None, include_none=True):
        source = self.to_dict()
        selected = columns or source.keys()
        return {
            key: source.get(key)
            for key in selected
            if include_none or source.get(key) is not None
        }


@dataclass(frozen=True)
class UserRole(DbModel):
    table_name: ClassVar[str] = "user_roles"

    id: Any = None
    email: Any = None
    role: Any = None
    active: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class Employee(DbModel):
    table_name: ClassVar[str] = "employees"
    primary_key: ClassVar[str] = "employee_id"

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

    id: Any = None
    action: Any = None
    case_id: Any = None
    user_email: Any = None
    remarks: Any = None
    created_at: Any = None


@dataclass(frozen=True)
class ApprovalUpload(DbModel):
    table_name: ClassVar[str] = "approval_uploads"

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

