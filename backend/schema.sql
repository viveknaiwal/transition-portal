CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  role text NOT NULL CHECK (role IN ('ADMIN', 'SUB_ADMIN', 'PAYROLL', 'MANAGER', 'HRBP')),
  active boolean DEFAULT true,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employees (
  employee_id text PRIMARY KEY,
  emp_code text,
  full_name text,
  company_email_id text,
  personal_email_id text,
  personal_mobile_no text,
  entity text,
  business_unit text,
  lob text,
  function text,
  sub_function text,
  region text,
  site_name text,
  grade text,
  band text,
  external_designation text,
  internal_designation text,
  l1_manager text,
  l1_manager_email text,
  l2_manager text,
  l2_manager_email text,
  hrbp_name text,
  hrbp_mail_id text,
  doj text,
  group_doj text,
  employee_status text,
  gender text,
  fixed_ctc numeric DEFAULT 0,
  variable numeric DEFAULT 0,
  pli numeric DEFAULT 0,
  retention numeric DEFAULT 0,
  total_ctc numeric DEFAULT 0,
  monthly_gross numeric DEFAULT 0,
  provident_fund numeric DEFAULT 0,
  gratuity numeric DEFAULT 0,
  medical_insurance numeric DEFAULT 0,
  email_check text,
  synced_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_employees_l1_manager_email ON employees(l1_manager_email);
CREATE INDEX IF NOT EXISTS idx_employees_company_email ON employees(company_email_id);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(employee_status);
CREATE INDEX IF NOT EXISTS idx_employees_emp_code ON employees(emp_code);

CREATE TABLE IF NOT EXISTS manager_overrides (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  emp_code text NOT NULL,
  manager_email text NOT NULL,
  added_by text,
  notes text,
  created_at timestamptz DEFAULT now(),
  UNIQUE(emp_code, manager_email)
);

CREATE TABLE IF NOT EXISTS separation_reasons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text UNIQUE NOT NULL,
  active boolean DEFAULT true,
  sort_order integer DEFAULT 0,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS separation_sub_reasons (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reason_id uuid REFERENCES separation_reasons(id) ON DELETE CASCADE,
  name text NOT NULL,
  active boolean DEFAULT true,
  sort_order integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  UNIQUE(reason_id, name)
);

CREATE TABLE IF NOT EXISTS option_values (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  option_group text NOT NULL,
  value text NOT NULL,
  active boolean DEFAULT true,
  sort_order integer DEFAULT 0,
  created_at timestamptz DEFAULT now(),
  UNIQUE(option_group, value)
);

CREATE TABLE IF NOT EXISTS cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_id text UNIQUE NOT NULL,
  emp_code text NOT NULL,
  emp_name text,
  official_email text,
  personal_email text,
  personal_contact text,
  entity text,
  business_unit text,
  lob text,
  function text,
  sub_function text,
  region text,
  site_name text,
  grade text,
  band text,
  external_designation text,
  internal_designation text,
  l1_manager text,
  l1_manager_email text,
  l2_manager text,
  l2_manager_email text,
  hrbp_name text,
  hrbp_mail_id text,
  doj text,
  group_doj text,
  employee_status text,
  fixed_ctc numeric,
  variable numeric,
  pli numeric,
  retention numeric,
  total_ctc numeric,
  monthly_gross numeric,
  provident_fund numeric,
  gratuity numeric,
  medical_insurance numeric,
  gender text,
  date_of_resignation text,
  last_working_date text,
  immediate_exit_or_serving_notice text,
  garden_leave text,
  separation_reason text,
  separation_sub_reason text,
  communication_status text,
  remarks text,
  approval_file_url text,
  approval_file_name text,
  rehire_status text,
  tenure text,
  tenure_served text,
  tenure_cohort text,
  ctc_cohort text,
  monthly_fixed_gross numeric,
  variable_pay_amount numeric,
  variable_days_prorata integer,
  notice_period_days integer,
  notice_period_amount numeric,
  severance_applicability text,
  severance_days integer,
  severance_pay_amount numeric,
  april_fy_2025 text,
  one_april_2025 text,
  status text DEFAULT 'Pending',
  closure_status text,
  admin_action text,
  admin_action_status text,
  admin_closed_status text,
  admin_closed_at timestamptz,
  admin_closed_by text,
  sent_back_at timestamptz,
  sent_back_by text,
  admin_remarks text,
  payroll_downloaded_at timestamptz,
  email_sent boolean DEFAULT false,
  email_sent_at timestamptz,
  email_sent_status text,
  created_at timestamptz DEFAULT now(),
  created_by text,
  created_by_role text,
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cases_emp_code ON cases(emp_code);
CREATE INDEX IF NOT EXISTS idx_cases_created_by ON cases(created_by);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_closure_status ON cases(closure_status);

CREATE TABLE IF NOT EXISTS audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  action text,
  case_id text,
  user_email text,
  remarks text,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approval_uploads (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  original_name text NOT NULL,
  stored_name text NOT NULL,
  content_type text,
  size_bytes integer DEFAULT 0,
  uploaded_by text,
  created_at timestamptz DEFAULT now()
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_cases_updated_at ON cases;
CREATE TRIGGER trg_cases_updated_at
BEFORE UPDATE ON cases
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
