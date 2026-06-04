import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER    = os.getenv("GMAIL_USER", "")
APP_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD", "")
FNF_EMAIL     = os.getenv("FNF_EMAIL", "")
TEST_MODE     = os.getenv("TEST_MODE", "true").lower() == "true"
ALLOWED_EMAILS = [e.strip().lower() for e in os.getenv("ALLOWED_TEST_EMAILS", "").split(",") if e.strip()]


def _send(to: list[str], subject: str, html: str, cc: list[str] = None):
    if not APP_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD not set in secrets — cannot send email.")

    # TEST_MODE safety: block emails to non-allowed addresses
    if TEST_MODE:
        all_recipients = [r.lower() for r in (to + (cc or []))]
        blocked = [r for r in all_recipients if r not in ALLOWED_EMAILS]
        if blocked:
            raise RuntimeError(
                f"TEST_MODE is ON — email blocked.\n"
                f"Blocked recipients: {', '.join(blocked)}\n"
                f"Allowed: {', '.join(ALLOWED_EMAILS)}\n"
                f"Set TEST_MODE=false in Streamlit Secrets to go live."
            )

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(to)
    if cc:
        msg["Cc"]  = ", ".join(cc)
    msg.attach(MIMEText(html, "html"))

    all_recipients = to + (cc or [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, APP_PASSWORD)
        s.sendmail(GMAIL_USER, all_recipients, msg.as_string())


def send_otp(email: str, otp: str):
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:420px;padding:24px;">
      <h2 style="color:#e31837;">Transition Portal — Login OTP</h2>
      <p>Your one-time password is:</p>
      <h1 style="letter-spacing:10px;color:#111;">{otp}</h1>
      <p style="color:#555;">Valid for 10 minutes. Do not share.</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    _send([email], "Transition Portal — Login OTP", html)


def send_case_created(case: dict):
    """Notify HRBP + L2 when a new case is submitted."""
    recipients = [r for r in [case.get("hrbp_mail_id"), case.get("l2_manager_email"), GMAIL_USER] if r]
    if not recipients:
        return
    name    = case.get("emp_name", "")
    case_id = case.get("case_id", "")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;padding:24px;">
      <h2 style="color:#e31837;">New Separation Case — {case_id}</h2>
      <p><b>Employee:</b> {name}<br/>
         <b>Last Working Date:</b> {case.get('last_working_date','')}<br/>
         <b>Reason:</b> {case.get('separation_reason','')}<br/>
         <b>Initiated by:</b> {case.get('created_by','')}</p>
      <p>Please review the case in the Transition Portal.</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    try:
        _send(recipients, f"[Transition Portal] New Case: {name} — {case_id}", html)
    except Exception:
        pass


def send_status_update(case: dict, new_status: str, remarks: str = ""):
    """Notify manager when admin updates case status."""
    recipients = [r for r in [case.get("l1_manager_email"), GMAIL_USER] if r]
    if not recipients:
        return
    name    = case.get("emp_name", "")
    case_id = case.get("case_id", "")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;padding:24px;">
      <h2 style="color:#e31837;">Case Update — {case_id}</h2>
      <p><b>Employee:</b> {name}<br/>
         <b>New Status:</b> <b>{new_status}</b><br/>
         {"<b>Remarks:</b> " + remarks if remarks else ""}</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    try:
        _send(recipients, f"[Transition Portal] {new_status}: {name} — {case_id}", html)
    except Exception:
        pass


def send_closure_email(case: dict):
    """
    Formal resignation confirmation email — exact template per spec.
    To: Personal Email | CC: Official Email, HRBP Mail ID
    """
    personal_email = case.get("personal_email") or case.get("personal_email_id", "")
    official_email = case.get("official_email") or case.get("company_email_id", "")
    hrbp_email     = case.get("hrbp_mail_id", "")

    if not personal_email:
        raise ValueError("Personal Email ID is blank — cannot send closure email.")
    if not official_email:
        raise ValueError("Official Email is blank.")

    cc = [r for r in [official_email, hrbp_email] if r]

    name     = case.get("emp_name", "")
    emp_code = case.get("emp_code", "")
    lwd      = case.get("last_working_date", "")
    sev_days = case.get("severance_days", 0) or 0
    not_days = case.get("notice_period_days", 0) or 0
    var_days = int(case.get("variable_days_prorata") or 0)
    var_flag = "Yes (prorata)" if var_days > 0 else "No (prorata)"

    html = f"""
<div style="font-family:Arial,sans-serif;color:#222;font-size:15px;line-height:1.7;max-width:640px;">
  <p>Dear {name},</p>

  <p>Following our discussion, this is to formally confirm that we have mutually agreed
     to conclude your employment with Cars24.</p>

  <p>We sincerely appreciate your contributions and the effort you've put into your role
     during your time with us.</p>

  <table style="border-collapse:collapse;margin:20px 0;width:100%;font-size:15px;">
    <tr style="background:#4736FE;">
      <th style="padding:12px 16px;border:1px solid #d1d5db;text-align:left;color:#fff;">Component</th>
      <th style="padding:12px 16px;border:1px solid #d1d5db;text-align:left;color:#fff;">Details</th>
    </tr>
    <tr>
      <td style="padding:10px 16px;border:1px solid #d1d5db;">Last Working Day (LWD)</td>
      <td style="padding:10px 16px;border:1px solid #d1d5db;">{lwd}</td>
    </tr>
    <tr style="background:#f9f9f9;">
      <td style="padding:10px 16px;border:1px solid #d1d5db;">Severance Pay</td>
      <td style="padding:10px 16px;border:1px solid #d1d5db;">{sev_days} days</td>
    </tr>
    <tr>
      <td style="padding:10px 16px;border:1px solid #d1d5db;">Notice Pay</td>
      <td style="padding:10px 16px;border:1px solid #d1d5db;">{not_days} days</td>
    </tr>
    <tr style="background:#f9f9f9;">
      <td style="padding:10px 16px;border:1px solid #d1d5db;">Variable</td>
      <td style="padding:10px 16px;border:1px solid #d1d5db;">{var_flag}</td>
    </tr>
  </table>

  <p><b>Note:</b></p>
  <p><b>Payment Timelines</b> (Subject to clearance from respective departments)</p>
  <ul>
    <li>LWD between 1st–15th: Exit Release Date by 21st</li>
    <li>LWD between 16th–30th/31st: Exit Release Date by 10th of the following month</li>
  </ul>

  <p>Should you need any assistance during this transition or wish to clarify any of the
     above points, please feel free to revert back on this email ID —
     <a href="mailto:transition.support@cars24.com">transition.support@cars24.com</a>.</p>

  <p>We wish you the very best for your future endeavors and thank you once again
     for your time at Cars24.</p>

  <p>Regards,<br/><b>People &amp; Culture Team</b><br/>Cars24</p>
</div>"""

    _send([personal_email], f"Confirmation of Resignation | {emp_code}", html, cc=cc)


def send_fnf_notification(case: dict):
    """Notify FNF team when a case is closed."""
    if not FNF_EMAIL:
        return
    name    = case.get("emp_name", "")
    case_id = case.get("case_id", "")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;padding:24px;">
      <h2 style="color:#e31837;">FNF Ready — {case_id}</h2>
      <p><b>Employee:</b> {name}<br/>
         <b>LWD:</b> {case.get('last_working_date','')}<br/>
         <b>Severance Days:</b> {case.get('severance_days', 0)}<br/>
         <b>Notice Period Days:</b> {case.get('notice_period_days', 0)}</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    try:
        _send([FNF_EMAIL], f"[FNF Ready] {name} — {case_id}", html)
    except Exception:
        pass
