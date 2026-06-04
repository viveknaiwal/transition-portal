import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER     = os.getenv("GMAIL_USER", "")
APP_PASSWORD   = os.getenv("GMAIL_APP_PASSWORD", "")
FNF_EMAIL      = os.getenv("FNF_EMAIL", "")


def _send(to: list[str], subject: str, html: str, cc: list[str] = None):
    if not APP_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD not set in .env — cannot send email")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.attach(MIMEText(html, "html"))
    all_recipients = to + (cc or [])
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, APP_PASSWORD)
        s.sendmail(GMAIL_USER, all_recipients, msg.as_string())


def send_otp(email: str, otp: str):
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:420px;padding:24px;">
      <h2 style="color:#e31837;">Transition Portal</h2>
      <p>Your one-time login code is:</p>
      <h1 style="letter-spacing:10px;color:#111;">{otp}</h1>
      <p style="color:#555;">Valid for 10 minutes. Do not share.</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    _send([email], "Transition Portal — Login OTP", html)


def send_case_created(case: dict):
    """Notify HRBP + L2 manager when a new case is initiated."""
    recipients = [r for r in [
        case.get("hrbp_mail_id"),
        case.get("l2_manager_email"),
        GMAIL_USER,
    ] if r]
    if not recipients:
        return
    name    = case.get("emp_name", "")
    case_id = case.get("case_id", "")
    lwd     = case.get("last_working_date", "")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;padding:24px;">
      <h2 style="color:#e31837;">New Separation Case — {case_id}</h2>
      <p><b>Employee:</b> {name}<br/>
         <b>Last Working Date:</b> {lwd}<br/>
         <b>Separation Reason:</b> {case.get('separation_reason','')}<br/>
         <b>Initiated by:</b> {case.get('created_by','')}</p>
      <p>Please review the case in the Transition Portal.</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    _send(recipients, f"[Transition Portal] New Case: {name} — {case_id}", html)


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
    _send(recipients, f"[Transition Portal] {new_status}: {name} — {case_id}", html)


def send_closure_email(case: dict):
    """Formal resignation confirmation to employee — mirrors GAS sendClosureEmail."""
    personal_email = case.get("personal_email") or case.get("personal_email_id", "")
    official_email = case.get("official_email") or case.get("company_email_id", "")
    hrbp_email     = case.get("hrbp_mail_id", "")
    if not personal_email:
        raise ValueError("Personal Email ID is blank — cannot send closure email.")
    if not official_email:
        raise ValueError("Official Email is blank.")
    if not hrbp_email:
        raise ValueError("HRBP Mail ID is blank.")

    name        = case.get("emp_name", "")
    emp_code    = case.get("emp_code", "")
    lwd         = case.get("last_working_date", "")
    sev_days    = case.get("severance_days", 0)
    notice_days = case.get("notice_period_days", 0)
    var_days    = int(case.get("variable_days_prorata") or 0)
    var_flag    = "Yes (prorata)" if var_days > 0 else "No"

    cc = [official_email, hrbp_email]
    if FNF_EMAIL and FNF_EMAIL not in cc:
        cc.append(FNF_EMAIL)

    html = f"""
    <div style="font-family:Arial,sans-serif;color:#222;font-size:15px;line-height:1.6;max-width:600px;">
      <p>Dear {name},</p>
      <p>Following our discussion, this is to formally confirm that we have mutually agreed to conclude
         your employment with Cars24. We sincerely appreciate your contributions during your time with us.</p>
      <table style="border-collapse:collapse;margin:20px 0;width:100%;">
        <tr style="background:#4736FE;color:#fff;">
          <th style="padding:12px 14px;border:1px solid #d1d5db;text-align:left;">Component</th>
          <th style="padding:12px 14px;border:1px solid #d1d5db;text-align:left;">Details</th>
        </tr>
        <tr><td style="padding:10px 14px;border:1px solid #d1d5db;">Last Working Day (LWD)</td><td style="padding:10px 14px;border:1px solid #d1d5db;">{lwd}</td></tr>
        <tr><td style="padding:10px 14px;border:1px solid #d1d5db;">Severance Pay</td><td style="padding:10px 14px;border:1px solid #d1d5db;">{sev_days} days</td></tr>
        <tr><td style="padding:10px 14px;border:1px solid #d1d5db;">Notice Pay</td><td style="padding:10px 14px;border:1px solid #d1d5db;">{notice_days} days</td></tr>
        <tr><td style="padding:10px 14px;border:1px solid #d1d5db;">Variable</td><td style="padding:10px 14px;border:1px solid #d1d5db;">{var_flag}</td></tr>
      </table>
      <p><b>Payment Timelines</b> (subject to clearances):<br>
         &bull; LWD 1st–15th → Exit Release by 21st<br>
         &bull; LWD 16th–31st → Exit Release by 10th of next month</p>
      <p>For assistance: <a href="mailto:transition.support@cars24.com">transition.support@cars24.com</a></p>
      <p>Regards,<br><b>People &amp; Culture Team</b><br>Cars24</p>
    </div>"""
    _send([personal_email], f"Confirmation of Resignation | {emp_code}", html, cc=cc)


def send_fnf_notification(case: dict):
    """Notify FNF team when a case is ready for full and final."""
    if not FNF_EMAIL:
        return
    name    = case.get("emp_name", "")
    case_id = case.get("case_id", "")
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:560px;padding:24px;">
      <h2 style="color:#e31837;">FNF Ready — {case_id}</h2>
      <p><b>Employee:</b> {name}<br/>
         <b>LWD:</b> {case.get('last_working_date','')}<br/>
         <b>Notice Period Amount:</b> ₹{case.get('notice_period_amount',0):,.2f}<br/>
         <b>Severance Pay:</b> ₹{case.get('severance_pay_amount',0):,.2f}<br/>
         <b>Variable Pay:</b> ₹{case.get('variable_pay_amount',0):,.2f}</p>
      <p>Please download the FNF report from the Transition Portal.</p>
      <hr/><p style="color:#999;font-size:12px;">Cars24 HR — Transition Portal</p>
    </div>"""
    _send([FNF_EMAIL], f"[FNF Ready] {name} — {case_id}", html)
