"""
notifications.py — Gmail SMTP shortage alerts via smtplib.
Logs each send to Firestore `notifications` (category: shortage_alert).
"""

from __future__ import annotations

import logging
import os
import smtplib
import traceback
import uuid
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Any

from dotenv import load_dotenv

from firebase_config import ATTENDANCE, NOTIFICATIONS, STUDENTS, SUBJECTS, db

load_dotenv()

# Print GMAIL_USER at startup for debugging
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "").strip()

logger = logging.getLogger(__name__)

if GMAIL_USER:
    pwd_preview = f"{GMAIL_PASSWORD[0]}***{GMAIL_PASSWORD[-1]}" if len(GMAIL_PASSWORD) > 2 else "***"
    logger.info(f"Gmail notifications initialized with user: {GMAIL_USER}")
    logger.info(f"Gmail password length: {len(GMAIL_PASSWORD)}, preview: {pwd_preview}")
    print(f"✓ Gmail notifications initialized with user: {GMAIL_USER}")
    print(f"✓ Gmail password length: {len(GMAIL_PASSWORD)}, preview: {pwd_preview}")
else:
    logger.warning("GMAIL_USER environment variable not set!")
    print("✗ WARNING: GMAIL_USER environment variable not set!")

SHORTAGE_CATEGORY = "shortage_alert"
EMAIL_SUBJECT = "⚠️ Attendance Shortage Warning - Ramaiah Institute of Technology"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _get_student_by_usn(usn: str) -> tuple[str | None, dict[str, Any] | None]:
    usn = (usn or "").upper()
    docs = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
    if not docs:
        return None, None
    return docs[0].id, docs[0].to_dict()


def _subject_display_name(subject_code: str) -> str:
    doc = db.collection(SUBJECTS).document(subject_code).get()
    if doc.exists:
        return doc.to_dict().get("name", subject_code)
    return subject_code


def subject_attendance_stats(usn: str, subject_code: str) -> tuple[int, float]:
    """Returns (total_sessions_marked, percentage). total 0 means no data yet."""
    usn = usn.upper()
    present = absent = 0
    for doc in db.collection(ATTENDANCE).where("usn", "==", usn).stream():
        d = doc.to_dict()
        if d.get("subject_code") != subject_code:
            continue
        if d.get("status") == "present":
            present += 1
        else:
            absent += 1
    total = present + absent
    if total == 0:
        return 0, 0.0
    return total, round((present / total) * 100, 1)


def compute_subject_attendance_pct(usn: str, subject_code: str) -> float:
    _, pct = subject_attendance_stats(usn, subject_code)
    return pct


def _log_alert_doc(
    *,
    alert_group_id: str,
    status: str,
    student_usn: str,
    student_name: str,
    student_id: str | None,
    subject_code: str,
    subject_name: str,
    attendance_pct: float,
    error_message: str | None = None,
) -> None:
    payload = {
        "category": SHORTAGE_CATEGORY,
        "alert_group_id": alert_group_id,
        "type": "email",
        "status": status,
        "timestamp": _now_iso(),
        "student_usn": student_usn,
        "student_name": student_name,
        "student_id": student_id,
        "subject_code": subject_code,
        "subject_name": subject_name,
        "attendance_pct": attendance_pct,
    }
    if error_message:
        payload["error_message"] = error_message
    db.collection(NOTIFICATIONS).add(payload)


def send_shortage_alert(
    usn: str,
    subject_code: str,
    attendance_pct: float | None = None,
) -> dict[str, Any]:
    """
    Send a shortage email when attendance for `subject_code` is below 75%.
    Returns summary; logs the attempt to Firestore.
    """
    usn = (usn or "").upper()
    subject_code = (subject_code or "").strip()
    sid, student = _get_student_by_usn(usn)
    if not student:
        return {"success": False, "message": "Student not found"}

    if attendance_pct is None:
        total_sessions, attendance_pct = subject_attendance_stats(usn, subject_code)
    else:
        total_sessions, _ = subject_attendance_stats(usn, subject_code)

    if total_sessions == 0:
        return {
            "success": True,
            "skipped": True,
            "message": "No attendance records for this subject yet; no alert sent",
            "attendance_pct": 0.0,
        }

    if attendance_pct >= 75:
        return {
            "success": True,
            "skipped": True,
            "message": "Attendance is at or above 75%; no alert sent",
            "attendance_pct": attendance_pct,
        }

    subject_name = _subject_display_name(subject_code)
    name = student.get("name", "Student")
    s_email = (student.get("email") or "").strip()

    alert_group_id = str(uuid.uuid4())
    email_status = "failed"
    email_error: str | None = None

    if not s_email:
        email_error = "No email on file"
        _log_alert_doc(
            alert_group_id=alert_group_id,
            status="failed",
            student_usn=usn,
            student_name=name,
            student_id=sid,
            subject_code=subject_code,
            subject_name=subject_name,
            attendance_pct=attendance_pct,
            error_message=email_error,
        )
    else:
        body = (
            f"Dear {name},\n\n"
            f"This is an automated attendance shortage warning from Ramaiah Institute of Technology.\n\n"
            f"Student name: {name}\n"
            f"Subject: {subject_name}\n"
            f"Current attendance: {attendance_pct}%\n\n"
            f"Your attendance in this subject is below the required 75%. "
            f"Please attend more classes regularly to avoid shortage and academic penalties.\n\n"
            f"If you believe this is an error, contact your class teacher or department office.\n\n"
            f"— FaceAttend, RIT"
        )
        try:
            # Configure SMTP connection exactly as specified
            smtp_server = 'smtp.gmail.com'
            port = 587
            server = smtplib.SMTP(smtp_server, port)
            server.ehlo()
            server.starttls()
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            
            # Build email message
            msg = MIMEMultipart()
            msg['From'] = GMAIL_USER
            msg['To'] = s_email
            msg['Subject'] = EMAIL_SUBJECT
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server.send_message(msg)
            server.quit()
            email_status = "sent"
            logger.info(f"Shortage alert email sent to {s_email} for {usn}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            email_error = str(exc)
            tb_str = traceback.format_exc()
            logger.error(f"Shortage alert email failed for {usn}:\n{tb_str}")
            print(f"ERROR: Email failed for {usn}: {exc}")
            print(tb_str)
        _log_alert_doc(
            alert_group_id=alert_group_id,
            status=email_status,
            student_usn=usn,
            student_name=name,
            student_id=sid,
            subject_code=subject_code,
            subject_name=subject_name,
            attendance_pct=attendance_pct,
            error_message=email_error,
        )

    return {
        "success": True,
        "skipped": False,
        "alert_group_id": alert_group_id,
        "attendance_pct": attendance_pct,
        "email_status": email_status,
        "email_error": email_error,
    }


def shortage_alert_firestore_rows(limit: int = 200) -> list[dict[str, Any]]:
    """Return shortage email alert rows for the teacher audit log."""
    docs = list(
        db.collection(NOTIFICATIONS)
        .where("category", "==", SHORTAGE_CATEGORY)
        .limit(limit)
        .stream()
    )
    rows: list[dict[str, Any]] = []
    for doc in docs:
        d = doc.to_dict()
        if d.get("type") != "email":
            continue
        rows.append(
            {
                "alert_group_id": d.get("alert_group_id") or doc.id,
                "timestamp": d.get("timestamp", ""),
                "student_name": d.get("student_name", ""),
                "student_usn": d.get("student_usn", ""),
                "subject_code": d.get("subject_code", ""),
                "subject_name": d.get("subject_name", ""),
                "attendance_pct": d.get("attendance_pct"),
                "email_status": d.get("status"),
                "error_message": d.get("error_message"),
            }
        )
    rows.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return rows[:limit]
