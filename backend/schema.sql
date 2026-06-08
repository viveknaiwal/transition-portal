CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL,
  email_blind_idx text UNIQUE,
  role text NOT NULL CHECK (role IN ('ADMIN', 'SUB_ADMIN', 'PAYROLL', 'MANAGER', 'HRBP')),
  active boolean DEFAULT true,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employees (
  employee_id text PRIMARY KEY,
  emp_code text,
  full_name text,
  full_name_blind_idx text,
  company_email_id text,
  company_email_id_blind_idx text,
  personal_email_id text,
  personal_email_id_blind_idx text,
  personal_mobile_no text,
  personal_mobile_no_blind_idx text,
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
  l1_manager_email_blind_idx text,
  l2_manager text,
  l2_manager_email text,
  l2_manager_email_blind_idx text,
  hrbp_name text,
  hrbp_mail_id text,
  hrbp_mail_id_blind_idx text,
  doj text,
  group_doj text,
  employee_status text,
  gender text,
  fixed_ctc text,
  variable text,
  pli text,
  retention text,
  total_ctc text,
  monthly_gross text,
  provident_fund text,
  gratuity text,
  medical_insurance text,
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
  manager_email_blind_idx text,
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
  emp_name_blind_idx text,
  official_email text,
  official_email_blind_idx text,
  personal_email text,
  personal_email_blind_idx text,
  personal_contact text,
  personal_contact_blind_idx text,
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
  l1_manager_email_blind_idx text,
  l2_manager text,
  l2_manager_email text,
  l2_manager_email_blind_idx text,
  hrbp_name text,
  hrbp_mail_id text,
  hrbp_mail_id_blind_idx text,
  doj text,
  group_doj text,
  employee_status text,
  fixed_ctc text,
  variable text,
  pli text,
  retention text,
  total_ctc text,
  monthly_gross text,
  provident_fund text,
  gratuity text,
  medical_insurance text,
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
  monthly_fixed_gross text,
  variable_pay_amount text,
  variable_days_prorata text,
  notice_period_days text,
  notice_period_amount text,
  severance_applicability text,
  severance_days text,
  severance_pay_amount text,
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
  created_by_blind_idx text,
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
  user_email_blind_idx text,
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
  uploaded_by_blind_idx text,
  created_at timestamptz DEFAULT now()
);

ALTER TABLE user_roles ADD COLUMN IF NOT EXISTS email_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS full_name_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS company_email_id_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS personal_email_id_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS personal_mobile_no_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS l1_manager_email_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS l2_manager_email_blind_idx text;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS hrbp_mail_id_blind_idx text;
ALTER TABLE manager_overrides ADD COLUMN IF NOT EXISTS manager_email_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS emp_name_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS official_email_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS personal_email_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS personal_contact_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS l1_manager_email_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS l2_manager_email_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS hrbp_mail_id_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS created_by_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS admin_closed_by_blind_idx text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS sent_back_by_blind_idx text;
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS user_email_blind_idx text;
ALTER TABLE approval_uploads ADD COLUMN IF NOT EXISTS uploaded_by_blind_idx text;

ALTER TABLE employees ALTER COLUMN fixed_ctc TYPE text USING fixed_ctc::text;
ALTER TABLE employees ALTER COLUMN variable TYPE text USING variable::text;
ALTER TABLE employees ALTER COLUMN pli TYPE text USING pli::text;
ALTER TABLE employees ALTER COLUMN retention TYPE text USING retention::text;
ALTER TABLE employees ALTER COLUMN total_ctc TYPE text USING total_ctc::text;
ALTER TABLE employees ALTER COLUMN monthly_gross TYPE text USING monthly_gross::text;
ALTER TABLE employees ALTER COLUMN provident_fund TYPE text USING provident_fund::text;
ALTER TABLE employees ALTER COLUMN gratuity TYPE text USING gratuity::text;
ALTER TABLE employees ALTER COLUMN medical_insurance TYPE text USING medical_insurance::text;
ALTER TABLE cases ALTER COLUMN fixed_ctc TYPE text USING fixed_ctc::text;
ALTER TABLE cases ALTER COLUMN variable TYPE text USING variable::text;
ALTER TABLE cases ALTER COLUMN pli TYPE text USING pli::text;
ALTER TABLE cases ALTER COLUMN retention TYPE text USING retention::text;
ALTER TABLE cases ALTER COLUMN total_ctc TYPE text USING total_ctc::text;
ALTER TABLE cases ALTER COLUMN monthly_gross TYPE text USING monthly_gross::text;
ALTER TABLE cases ALTER COLUMN provident_fund TYPE text USING provident_fund::text;
ALTER TABLE cases ALTER COLUMN gratuity TYPE text USING gratuity::text;
ALTER TABLE cases ALTER COLUMN medical_insurance TYPE text USING medical_insurance::text;
ALTER TABLE cases ALTER COLUMN monthly_fixed_gross TYPE text USING monthly_fixed_gross::text;
ALTER TABLE cases ALTER COLUMN variable_pay_amount TYPE text USING variable_pay_amount::text;
ALTER TABLE cases ALTER COLUMN variable_days_prorata TYPE text USING variable_days_prorata::text;
ALTER TABLE cases ALTER COLUMN notice_period_days TYPE text USING notice_period_days::text;
ALTER TABLE cases ALTER COLUMN notice_period_amount TYPE text USING notice_period_amount::text;
ALTER TABLE cases ALTER COLUMN severance_days TYPE text USING severance_days::text;
ALTER TABLE cases ALTER COLUMN severance_pay_amount TYPE text USING severance_pay_amount::text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_roles_email_blind_unique ON user_roles(email_blind_idx);
CREATE INDEX IF NOT EXISTS idx_employees_l1_manager_email_blind ON employees(l1_manager_email_blind_idx);
CREATE INDEX IF NOT EXISTS idx_employees_company_email_blind ON employees(company_email_id_blind_idx);
CREATE INDEX IF NOT EXISTS idx_manager_overrides_manager_email_blind ON manager_overrides(manager_email_blind_idx);
CREATE INDEX IF NOT EXISTS idx_cases_created_by_blind ON cases(created_by_blind_idx);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_email_blind ON audit_log(user_email_blind_idx);
CREATE INDEX IF NOT EXISTS idx_approval_uploads_uploaded_by_blind ON approval_uploads(uploaded_by_blind_idx);

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
