"""
routes/forgot_password.py  —  Email OTP-based password reset for admin, teacher, and student users.
"""

import random
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_mail import Mail, Message

from firebase_config import STUDENTS, TEACHERS, USERS, db

forgot_password_bp = Blueprint("forgot_password", __name__)

PASSWORD_RESETS = "password_resets"


def _find_user_by_email(email: str):
    email = email.strip().lower()
    if not email:
        return None, None, None

    # Admin user in users collection
    docs = list(db.collection(USERS).where("role", "==", "admin").where("email", "==", email).limit(1).stream())
    if docs:
        return docs[0].reference, docs[0].to_dict(), "admin"

    # Teacher user
    docs = list(db.collection(TEACHERS).where("email", "==", email).limit(1).stream())
    if docs:
        return docs[0].reference, docs[0].to_dict(), "teacher"

    # Student user
    docs = list(db.collection(STUDENTS).where("email", "==", email).limit(1).stream())
    if docs:
        return docs[0].reference, docs[0].to_dict(), "student"

    return None, None, None


def _find_student_by_usn(usn: str):
    usn = usn.strip().upper()
    if not usn:
        return None, None

    doc = db.collection(STUDENTS).document(usn).get()
    if doc.exists:
        return doc.reference, doc.to_dict()

    docs = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
    if docs:
        return docs[0].reference, docs[0].to_dict()
    return None, None


def _find_teacher_by_email(email: str):
    email = email.strip().lower()
    if not email:
        return None, None
    docs = list(db.collection(TEACHERS).where("email", "==", email).limit(1).stream())
    if docs:
        return docs[0].reference, docs[0].to_dict()
    return None, None


def _find_student_by_email(email: str):
    email = email.strip().lower()
    if not email:
        return None, None
    docs = list(db.collection(STUDENTS).where("email", "==", email).limit(1).stream())
    if docs:
        return docs[0].reference, docs[0].to_dict()
    return None, None


def _is_expired(expires_at) -> bool:
    if not expires_at:
        return True
    now = datetime.now(timezone.utc) if getattr(expires_at, "tzinfo", None) else datetime.utcnow()
    return now > expires_at


def _update_password_from_reset(email_or_usn: str, reset_data: dict, new_password: str) -> bool:
    user_type = (reset_data.get("user_type") or "").strip().lower()
    email = (reset_data.get("email") or "").strip().lower()
    usn = (reset_data.get("usn") or "").strip().upper()

    if user_type == "teacher":
        target_ref, _ = _find_teacher_by_email(email or email_or_usn)
        if target_ref:
            target_ref.update({"password": new_password})
            return True

    if user_type == "student":
        target_ref = None
        if usn:
            target_ref, _ = _find_student_by_usn(usn)
        if not target_ref and email:
            target_ref, _ = _find_student_by_email(email)
        if target_ref:
            target_ref.update({"password": new_password})
            return True

    if user_type == "admin":
        target_ref, _, _ = _find_user_by_email(email or email_or_usn)
        if target_ref:
            target_ref.update({"password": new_password})
            return True

    if "@" in email_or_usn:
        target_ref, _, _ = _find_user_by_email(email_or_usn)
        if target_ref:
            target_ref.update({"password": new_password})
            return True
    else:
        target_ref, _ = _find_student_by_usn(email_or_usn)
        if target_ref:
            target_ref.update({"password": new_password})
            return True

    return False


def _send_reset_email(email: str, otp: str, user_type: str, display_name: str | None = None):
    msg = Message(
        subject="FaceAttend password reset code",
        recipients=[email],
        body=(
            f"Hello {display_name or 'User'},\n\n"
            f"Your FaceAttend password reset code is: {otp}\n"
            f"This code expires in 10 minutes.\n\n"
            "If you did not request this code, please ignore this email.\n\n"
            "— FaceAttend"
        ),
    )
    Mail(current_app).send(msg)


@forgot_password_bp.route("/forgot-password", methods=["POST"])
def request_password_reset():
    data = request.json or {}
    email = (data.get("email") or "").strip()
    usn = (data.get("usn") or "").strip().upper()

    if not email and not usn:
        return jsonify({"success": False, "message": "Email or USN is required"}), 400

    target_ref = None
    target_data = None
    target_type = None
    recipient_email = None
    recipient_usn = None
    display_name = None

    if email:
        target_ref, target_data, target_type = _find_user_by_email(email)
        if not target_ref:
            return jsonify({"success": False, "message": "No user found with that email"}), 404
        recipient_email = email.lower()
        recipient_usn = (target_data.get("usn") or target_data.get("teacher_id") or "").strip().upper()
        display_name = target_data.get("name")
    else:
        target_ref, target_data = _find_student_by_usn(usn)
        if not target_ref:
            return jsonify({"success": False, "message": "No student found with that USN"}), 404
        recipient_email = (target_data.get("email") or "").strip().lower()
        if not recipient_email:
            return jsonify({"success": False, "message": "Student does not have an email on file"}), 400
        recipient_usn = usn
        target_type = "student"
        display_name = target_data.get("name")

    otp = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    key = email.lower() if email else usn

    db.collection(PASSWORD_RESETS).document(key).set({
        "otp": otp,
        "email": recipient_email,
        "usn": recipient_usn,
        "expires_at": expires_at,
        "requested_at": datetime.utcnow(),
        "user_type": target_type,
    })

    try:
        _send_reset_email(recipient_email, otp, target_type, display_name)
    except Exception as exc:
        current_app.logger.exception("Failed to send password reset email to %s", recipient_email)
        return jsonify({"success": False, "message": str(exc)}), 500

    return jsonify({"success": True, "message": "OTP sent to your email"})


@forgot_password_bp.route("/verify-otp", methods=["POST"])
def verify_reset_otp():
    data = request.json or {}
    email_or_usn = (data.get("email_or_usn") or "").strip()
    otp = (data.get("otp") or "").strip()
    new_password = (data.get("new_password") or "").strip()

    if not email_or_usn or not otp or not new_password:
        return jsonify({"success": False, "message": "Email/USN, OTP and new password are required"}), 400

    key = email_or_usn.lower() if "@" in email_or_usn else email_or_usn.upper()
    doc = db.collection(PASSWORD_RESETS).document(key).get()
    if not doc.exists:
        return jsonify({"success": False, "message": "Invalid or expired OTP"}), 400

    reset_data = doc.to_dict() or {}
    if str(reset_data.get("otp")) != otp:
        return jsonify({"success": False, "message": "Invalid OTP"}), 400

    expires_at = reset_data.get("expires_at")
    if _is_expired(expires_at):
        db.collection(PASSWORD_RESETS).document(key).delete()
        return jsonify({"success": False, "message": "OTP has expired"}), 400

    if not _update_password_from_reset(email_or_usn, reset_data, new_password):
        return jsonify({"success": False, "message": "Could not find the account to update"}), 404

    db.collection(PASSWORD_RESETS).document(key).delete()
    return jsonify({"success": True, "message": "Password updated successfully"})
