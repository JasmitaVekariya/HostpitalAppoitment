"""
Email notification service for Sunrise Multispeciality Hospital.
Uses Gmail SMTP to send HTML-formatted emails for key appointment lifecycle events.
"""
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import date, time
from typing import Optional
from backend.config import settings


# ─────────────────────────────────────────────
# Core SMTP Send (runs in background thread)
# ─────────────────────────────────────────────

def _send_email_sync(to_address: str, subject: str, html_body: str, text_body: str = "") -> None:
    """Low-level SMTP send with up to 3 retry attempts. Called in a background thread."""
    if not settings.EMAIL_USER or not settings.EMAIL_PASSWORD:
        print("[EMAIL] Email credentials not configured – skipping send.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Sunrise Hospital <{settings.EMAIL_USER}>"
    msg["To"] = to_address

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                server.login(settings.EMAIL_USER, settings.EMAIL_PASSWORD)
                server.sendmail(settings.EMAIL_USER, to_address, msg.as_string())
            print(f"[EMAIL] ✅ Sent '{subject}' to {to_address} (attempt {attempt})")
            return  # success — stop retrying
        except Exception as e:
            print(f"[EMAIL] ⚠️ Attempt {attempt}/{max_attempts} failed for {to_address}: {e}")
            if attempt < max_attempts:
                import time
                time.sleep(2)  # brief pause before next attempt

    print(f"[EMAIL] ❌ All {max_attempts} attempts failed. Email to {to_address} could not be delivered.")



def send_email(to_address: str, subject: str, html_body: str, text_body: str = "") -> None:
    """Fire-and-forget email send in a daemon background thread."""
    thread = threading.Thread(
        target=_send_email_sync,
        args=(to_address, subject, html_body, text_body),
        daemon=True
    )
    thread.start()


# ─────────────────────────────────────────────
# Shared HTML Layout
# ─────────────────────────────────────────────

def _wrap_html(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:32px 0;">
    <tr>
      <td align="center">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,#1e3a5f 0%,#2d6a9f 100%);padding:32px 40px;text-align:center;">
              <h1 style="margin:0;color:#ffffff;font-size:24px;font-weight:700;letter-spacing:0.5px;">🏥 Sunrise Multispeciality Hospital</h1>
              <p style="margin:6px 0 0;color:#a8d4f5;font-size:13px;">Your Health, Our Priority</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:36px 40px;">
              {body_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;text-align:center;">
              <p style="margin:0;color:#94a3b8;font-size:12px;">
                Sunrise Multispeciality Hospital · 123 Health Avenue, Gujarat, India<br>
                📞 +91-9000000000 · 📧 reception@sunrisehospital.com
              </p>
              <p style="margin:8px 0 0;color:#cbd5e1;font-size:11px;">
                This is an automated message. Please do not reply to this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _info_row(label: str, value: str) -> str:
    return f"""
    <tr>
      <td style="padding:8px 12px;font-size:14px;color:#64748b;font-weight:600;width:140px;vertical-align:top;">{label}</td>
      <td style="padding:8px 12px;font-size:14px;color:#1e293b;font-weight:500;">{value}</td>
    </tr>"""


# ─────────────────────────────────────────────
# 1. Booking Confirmation
# ─────────────────────────────────────────────

def send_booking_confirmation(
    patient_email: str,
    patient_name: str,
    doctor_name: str,
    specialization: str,
    department: str,
    appointment_date: date,
    appointment_time: time,
    symptoms: str = "",
    floor: Optional[str] = None,
) -> None:
    date_str = appointment_date.strftime("%A, %B %d, %Y")
    time_str = appointment_time.strftime("%I:%M %p")
    floor_str = f"Floor {floor}" if floor else "Please check at reception"

    body = f"""
    <h2 style="color:#1e3a5f;margin:0 0 8px;">✅ Appointment Confirmed!</h2>
    <p style="color:#475569;font-size:15px;margin:0 0 24px;">
      Dear <strong>{patient_name}</strong>, your appointment has been successfully booked at Sunrise Multispeciality Hospital.
    </p>

    <div style="background:#f0f9ff;border-left:4px solid #2d6a9f;border-radius:8px;padding:20px 16px;margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        {_info_row("👨‍⚕️ Doctor", doctor_name)}
        {_info_row("🩺 Specialization", specialization)}
        {_info_row("🏢 Department", department)}
        {_info_row("📅 Date", date_str)}
        {_info_row("⏰ Time", time_str)}
        {_info_row("📍 Location", floor_str)}
        {_info_row("🩹 Symptoms", symptoms if symptoms else "—") if symptoms else ""}
      </table>
    </div>

    <div style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:8px;padding:16px;margin-bottom:24px;">
      <p style="margin:0;color:#065f46;font-size:14px;font-weight:600;">📋 What to bring:</p>
      <ul style="margin:8px 0 0;padding-left:20px;color:#047857;font-size:14px;line-height:1.8;">
        <li>Government-issued photo ID</li>
        <li>Previous medical records (if any)</li>
        <li>List of current medications</li>
        <li>Arrive 10 minutes before your appointment</li>
      </ul>
    </div>

    <p style="color:#64748b;font-size:13px;text-align:center;">
      Need to reschedule or cancel? Log in to the patient portal or contact us at <strong>+91-9000000000</strong>.
    </p>
    """

    subject = f"✅ Appointment Confirmed – {date_str} at {time_str}"
    send_email(patient_email, subject, _wrap_html("Appointment Confirmed", body),
               f"Dear {patient_name}, your appointment with {doctor_name} is confirmed on {date_str} at {time_str}.")


# ─────────────────────────────────────────────
# 2. Appointment Rescheduled
# ─────────────────────────────────────────────

def send_reschedule_confirmation(
    patient_email: str,
    patient_name: str,
    doctor_name: str,
    specialization: str,
    new_date: date,
    new_time: time,
    old_date: Optional[date] = None,
    old_time: Optional[time] = None,
) -> None:
    new_date_str = new_date.strftime("%A, %B %d, %Y")
    new_time_str = new_time.strftime("%I:%M %p")
    old_str = ""
    if old_date and old_time:
        old_str = _info_row("🗓️ Previous Slot", f"{old_date.strftime('%B %d, %Y')} at {old_time.strftime('%I:%M %p')}")

    body = f"""
    <h2 style="color:#7c3aed;margin:0 0 8px;">🔄 Appointment Rescheduled</h2>
    <p style="color:#475569;font-size:15px;margin:0 0 24px;">
      Dear <strong>{patient_name}</strong>, your appointment has been successfully rescheduled.
    </p>

    <div style="background:#faf5ff;border-left:4px solid #7c3aed;border-radius:8px;padding:20px 16px;margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        {_info_row("👨‍⚕️ Doctor", doctor_name)}
        {_info_row("🩺 Specialization", specialization)}
        {old_str}
        {_info_row("📅 New Date", new_date_str)}
        {_info_row("⏰ New Time", new_time_str)}
      </table>
    </div>

    <p style="color:#64748b;font-size:13px;text-align:center;">
      If you did not request this change, please contact us immediately at <strong>+91-9000000000</strong>.
    </p>
    """

    subject = f"🔄 Appointment Rescheduled – {new_date_str} at {new_time_str}"
    send_email(patient_email, subject, _wrap_html("Appointment Rescheduled", body),
               f"Dear {patient_name}, your appointment with {doctor_name} has been rescheduled to {new_date_str} at {new_time_str}.")


# ─────────────────────────────────────────────
# 3. Appointment Cancelled
# ─────────────────────────────────────────────

def send_cancellation_notice(
    patient_email: str,
    patient_name: str,
    doctor_name: str,
    appointment_date: date,
    appointment_time: time,
) -> None:
    date_str = appointment_date.strftime("%A, %B %d, %Y")
    time_str = appointment_time.strftime("%I:%M %p")

    body = f"""
    <h2 style="color:#dc2626;margin:0 0 8px;">❌ Appointment Cancelled</h2>
    <p style="color:#475569;font-size:15px;margin:0 0 24px;">
      Dear <strong>{patient_name}</strong>, your appointment has been cancelled as requested.
    </p>

    <div style="background:#fef2f2;border-left:4px solid #dc2626;border-radius:8px;padding:20px 16px;margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        {_info_row("👨‍⚕️ Doctor", doctor_name)}
        {_info_row("📅 Cancelled Date", date_str)}
        {_info_row("⏰ Cancelled Time", time_str)}
      </table>
    </div>

    <div style="background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:16px;margin-bottom:24px;">
      <p style="margin:0;color:#92400e;font-size:14px;">
        💡 <strong>Need care?</strong> You can book a new appointment anytime through our patient portal or call <strong>+91-9000000000</strong>.
      </p>
    </div>

    <p style="color:#64748b;font-size:13px;text-align:center;">
      If you did not request this cancellation, please contact us immediately.
    </p>
    """

    subject = f"❌ Appointment Cancelled – {date_str}"
    send_email(patient_email, subject, _wrap_html("Appointment Cancelled", body),
               f"Dear {patient_name}, your appointment with {doctor_name} on {date_str} at {time_str} has been cancelled.")


# ─────────────────────────────────────────────
# 4. Appointment Completed (Doctor Summary)
# ─────────────────────────────────────────────

def send_completion_summary(
    patient_email: str,
    patient_name: str,
    doctor_name: str,
    appointment_date: date,
    doctor_notes: Optional[str] = None,
) -> None:
    date_str = appointment_date.strftime("%A, %B %d, %Y")
    notes_section = ""
    if doctor_notes:
        notes_section = f"""
        <div style="background:#f0fdf4;border-left:4px solid #16a34a;border-radius:8px;padding:20px 16px;margin-bottom:24px;">
          <p style="margin:0 0 8px;color:#15803d;font-size:14px;font-weight:600;">📝 Doctor's Notes:</p>
          <p style="margin:0;color:#166534;font-size:14px;line-height:1.7;">{doctor_notes}</p>
        </div>"""

    body = f"""
    <h2 style="color:#15803d;margin:0 0 8px;">✔️ Appointment Completed</h2>
    <p style="color:#475569;font-size:15px;margin:0 0 24px;">
      Dear <strong>{patient_name}</strong>, thank you for visiting Sunrise Multispeciality Hospital on <strong>{date_str}</strong>.
    </p>

    <div style="background:#f0fdf4;border-left:4px solid #16a34a;border-radius:8px;padding:20px 16px;margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        {_info_row("👨‍⚕️ Doctor", doctor_name)}
        {_info_row("📅 Visit Date", date_str)}
      </table>
    </div>

    {notes_section}

    <p style="color:#64748b;font-size:13px;text-align:center;">
      We hope you're feeling better soon! For follow-up appointments or queries, contact us at <strong>+91-9000000000</strong>.
    </p>
    """

    subject = f"✔️ Visit Summary – {date_str} | Sunrise Hospital"
    send_email(patient_email, subject, _wrap_html("Visit Completed", body),
               f"Dear {patient_name}, thank you for your visit with {doctor_name} on {date_str}.")

# ─────────────────────────────────────────────
# 5. Human-in-the-Loop Review Request
# ─────────────────────────────────────────────

def send_human_review_request(
    to_address: str,
    patient_name: str,
    age: str,
    symptoms: str,
    review_id: str,
    review_type: str
) -> None:
    body = f"""
    <h2 style="color:#b91c1c;margin:0 0 8px;">⚠️ Doctor Review Required</h2>
    <p style="color:#475569;font-size:15px;margin:0 0 24px;">
      An AI triage session requires human review. Type: <strong>{review_type}</strong>
    </p>

    <div style="background:#fef2f2;border-left:4px solid #ef4444;border-radius:8px;padding:20px 16px;margin-bottom:24px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        {_info_row("👤 Patient Name", patient_name)}
        {_info_row("🎂 Age", age)}
        {_info_row("🩹 Symptoms", symptoms)}
        {_info_row("🆔 Review ID", review_id)}
      </table>
    </div>

    <div style="text-align:center; margin-bottom: 24px;">
        <p style="color:#1e293b;font-weight:600;margin-bottom:16px;">Please select an action to resume the patient's session:</p>
        
        <a href="{settings.FRONTEND_URL}/api/human-review/{review_id}/APPROVE" style="display:inline-block; padding:10px 20px; background-color:#10b981; color:white; text-decoration:none; border-radius:6px; font-weight:bold; margin-right:10px;">APPROVE</a>
        
        <a href="{settings.FRONTEND_URL}/api/human-review/{review_id}/REJECT" style="display:inline-block; padding:10px 20px; background-color:#f59e0b; color:white; text-decoration:none; border-radius:6px; font-weight:bold; margin-right:10px;">REJECT</a>
        
        <a href="{settings.FRONTEND_URL}/api/human-review/{review_id}/EMERGENCY" style="display:inline-block; padding:10px 20px; background-color:#ef4444; color:white; text-decoration:none; border-radius:6px; font-weight:bold;">EMERGENCY</a>
    </div>

    <p style="color:#64748b;font-size:13px;text-align:center;">
      This link is one-time use and will instantly resume the patient's chat session.
    </p>
    """

    subject = f"⚠️ Action Required: AI Triage Review ({review_type})"
    send_email(to_address, subject, _wrap_html("Action Required", body),
               f"Doctor Review Required for {patient_name}. Review ID: {review_id}. Please check your HTML email to approve/reject.")

