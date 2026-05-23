"""
routes/auth.py  —  Authentication (admin / teacher / student)
POST /api/auth/login   — credentials checked per role
POST /api/auth/logout  — clear session
"""

from flask import Blueprint, jsonify, request, session

from firebase_config import STUDENTS, TEACHERS, USERS, db

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    email = (data.get("email") or "").strip()
    password = (data.get("password") or "").strip()
    role = (data.get("role") or "").strip().lower()

    if not role or not password:
        return jsonify({"success": False, "message": "Role and password are required"}), 400

    # ── Admin (email + password → users where role=admin) ─────────────────────
    if role == "admin":
        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400
        docs = list(
            db.collection(USERS)
            .where("role", "==", "admin")
            .where("email", "==", email.lower())
            .limit(1)
            .stream()
        )
        if not docs:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401
        doc = docs[0]
        admin = doc.to_dict()
        if admin.get("password") != password:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401
        return jsonify({
            "success": True,
            "user": {
                "id": doc.id,
                "name": admin.get("name", "Administrator"),
                "email": admin.get("email"),
                "role": "admin",
            },
        })

    # ── Teacher (email + password → teachers collection) ──────────────────────
    if role == "teacher":
        if not email:
            return jsonify({"success": False, "message": "Email is required"}), 400
        docs = list(
            db.collection(TEACHERS)
            .where("email", "==", email.lower())
            .limit(1)
            .stream()
        )
        if not docs:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401
        doc = docs[0]
        t = doc.to_dict()
        if t.get("password") != password:
            return jsonify({"success": False, "message": "Invalid email or password"}), 401
        return jsonify({
            "success": True,
            "user": {
                "id": doc.id,
                "name": t.get("name"),
                "email": t.get("email"),
                "role": "teacher",
                "department": t.get("department", ""),
                "teacherId": doc.id,
                "semester": t.get("semester", ""),
                "assignedSubject": {
                    "code": t.get("subject_code"),
                    "name": t.get("subject_name"),
                },
                "subject_code": t.get("subject_code"),
            },
        })

    # ── Student (USN + password → students collection) ────────────────────────
    if role == "student":
        usn = (email or "").upper()
        if not usn:
            return jsonify({"success": False, "message": "USN is required"}), 400
        doc = db.collection(STUDENTS).document(usn).get()
        if not doc.exists:
            q = db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream()
            docs = list(q)
            if not docs:
                return jsonify({"success": False, "message": "Invalid USN or password"}), 401
            doc = docs[0]
        s = doc.to_dict()
        if s.get("password") != password:
            return jsonify({"success": False, "message": "Invalid USN or password"}), 401
        return jsonify({
            "success": True,
            "user": {
                "id": doc.id,
                "name": s.get("name"),
                "email": s.get("email", ""),
                "role": "student",
                "usn": s.get("usn", usn),
                "branch": s.get("branch", s.get("department", "")),
                "semester": s.get("semester", ""),
                "section": s.get("section", ""),
                "phone": s.get("phone", ""),
            },
        })

    return jsonify({"success": False, "message": "Invalid role"}), 400


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})
