"""
routes/notifications.py  —  Firestore backend + shortage email audit log

Fixed paths must be registered before /<user_id> so names are not captured as IDs.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request

from firebase_config import NOTIFICATIONS, db
from services.notifications import send_shortage_alert, shortage_alert_firestore_rows

notifications_bp = Blueprint("notifications", __name__)


# ── Shortage alert (email) ────────────────────────────────────────────────────
@notifications_bp.route("/shortage-alerts-log", methods=["GET"])
def shortage_alerts_log():
    limit = min(int(request.args.get("limit", 200)), 500)
    return jsonify({"alerts": shortage_alert_firestore_rows(limit)})


@notifications_bp.route("/send-shortage-alert", methods=["POST"])
def send_shortage_alert_route():
    data = request.json or {}
    usn = data.get("usn", "")
    subject_code = data.get("subject_code", "")
    raw_pct = data.get("attendance_pct")
    pct = float(raw_pct) if raw_pct is not None and str(raw_pct) != "" else None

    result = send_shortage_alert(usn, subject_code, pct)
    if not result.get("success"):
        return jsonify(result), 404
    return jsonify(result), 200


@notifications_bp.route("/test-email", methods=["POST"])
def test_email():
    import os
    import smtplib
    import traceback
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    from dotenv import load_dotenv

    load_dotenv()
    
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_password = os.environ.get("GMAIL_PASSWORD", "").strip()
    
    # Debug output
    print(f"\n=== EMAIL DEBUG ===")
    print(f"GMAIL_USER: {repr(gmail_user)}")
    print(f"GMAIL_PASSWORD length: {len(gmail_password)}")
    print(f"GMAIL_PASSWORD repr: {repr(gmail_password)}")
    print(f"GMAIL_PASSWORD bytes: {gmail_password.encode('utf-8')}")
    print(f"=== END DEBUG ===\n")
    
    if not gmail_user or not gmail_password:
        return jsonify({"success": False, "message": "GMAIL_USER or GMAIL_PASSWORD not configured"}), 500

    try:
        # Configure SMTP connection exactly as specified
        smtp_server = 'smtp.gmail.com'
        port = 587
        server = smtplib.SMTP(smtp_server, port)
        server.ehlo()
        server.starttls()
        print(f"Attempting login with user: {gmail_user}")
        server.login(gmail_user, gmail_password)
        
        # Build email message
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = gmail_user
        msg['Subject'] = "FaceAttend test email"
        body = (
            "This is a test email from FaceAttend.\n\n"
            "If you receive this message, Gmail SMTP is configured correctly.\n\n"
            "— FaceAttend"
        )
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        return jsonify({"success": True, "message": "Test email sent successfully"})
    except Exception as exc:
        tb_str = traceback.format_exc()
        from flask import current_app
        current_app.logger.error(f"Test email failed:\n{tb_str}")
        print(f"ERROR: Test email failed: {exc}")
        print(tb_str)
        return jsonify({"success": False, "message": str(exc)}), 500


# ── Student shortage alert history ───────────────────────────────────────────
@notifications_bp.route("/student-shortage/<usn>", methods=["GET"])
def student_shortage_notifications(usn):
    usn = usn.upper()
    limit = min(int(request.args.get("limit", 100)), 500)
    rows = [
        r for r in shortage_alert_firestore_rows(limit * 2)
        if (r.get("student_usn") or "").upper() == usn
    ]
    return jsonify({"notifications": rows[:limit]})


# ── Get notifications for a user ─────────────────────────────────────────────
@notifications_bp.route("/<user_id>", methods=["GET"])
def get_notifications(user_id):
    role = request.args.get("role", "student")
    docs = (
        db.collection(NOTIFICATIONS)
        .where("user_id", "==", user_id)
        .where("user_role", "==", role)
        .order_by("timestamp", direction="DESCENDING")
        .limit(50)
        .stream()
    )
    return jsonify(
        [
            {
                "id": doc.id,
                "type": doc.to_dict().get("type", "info"),
                "title": doc.to_dict().get("title", ""),
                "message": doc.to_dict().get("message", ""),
                "timestamp": doc.to_dict().get("timestamp", ""),
                "read": bool(doc.to_dict().get("read", False)),
            }
            for doc in docs
        ]
    )


# ── Mark one notification as read ───────────────────────────────────────────
@notifications_bp.route("/mark-read/<notif_id>", methods=["POST"])
def mark_read(notif_id):
    db.collection(NOTIFICATIONS).document(notif_id).update({"read": True})
    return jsonify({"success": True})


# ── Mark all read for a user (bonus) ────────────────────────────────────────
@notifications_bp.route("/mark-all-read", methods=["POST"])
def mark_all_read():
    data = request.json or {}
    user_id = data.get("user_id", "")
    docs = db.collection(NOTIFICATIONS).where("user_id", "==", user_id).stream()
    batch = db.batch()
    for doc in docs:
        batch.update(doc.reference, {"read": True})
    batch.commit()
    return jsonify({"success": True})


# ── Send a notification (bonus) ───────────────────────────────────────────
@notifications_bp.route("/send", methods=["POST"])
def send_notification():
    data = request.json or {}
    db.collection(NOTIFICATIONS).add(
        {
            "user_id": data.get("user_id"),
            "user_role": data.get("user_role", "student"),
            "type": data.get("type", "info"),
            "title": data.get("title", ""),
            "message": data.get("message", ""),
            "timestamp": datetime.now().strftime("%I:%M %p Today"),
            "read": False,
        }
    )
    return jsonify({"success": True})


# ── Unread count (bonus) ──────────────────────────────────────────────────
@notifications_bp.route("/unread-count/<user_id>", methods=["GET"])
def unread_count(user_id):
    docs = (
        db.collection(NOTIFICATIONS)
        .where("user_id", "==", user_id)
        .where("read", "==", False)
        .stream()
    )
    count = sum(1 for _ in docs)
    return jsonify({"count": count})
