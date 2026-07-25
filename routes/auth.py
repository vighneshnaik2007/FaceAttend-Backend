"""
routes/auth.py  —  Authentication (admin / teacher / student)
POST /api/auth/login   — credentials checked per role
POST /api/auth/logout  — clear session
"""

from flask import Blueprint, jsonify, request, session

from firebase_config import STUDENTS, TEACHERS, USERS, db

auth_bp = Blueprint("auth", __name__)


def _norm_semester(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _norm_section(value) -> str:
    return str(value or "").strip().upper()


def _teacher_assignments(t: dict) -> list[dict]:
    assignments = t.get("assignments")
    if isinstance(assignments, list) and assignments:
        return [a for a in assignments if isinstance(a, dict)]
    semester = _norm_semester(t.get("semester"))
    section = _norm_section(t.get("section"))
    if not semester and not section:
        return []
    return [{
        "semester": semester,
        "section": section,
        "subject_code": t.get("subject_code", ""),
        "subject_name": t.get("subject_name", ""),
        "department": t.get("department", ""),
    }]


def _get_teacher_sections(teacher_id: str) -> list[dict]:
    """Query a teacher document and return explicit section records.

    Returns exactly:
      [{"id": "SEM2_C", "section_name": "Section C", "semester": "Semester 2",
        "subject": "ESC232 — Mechanical Engineering"}, ...]
    """
    doc = db.collection(TEACHERS).document(teacher_id).get()
    if not doc.exists:
        q = list(db.collection(TEACHERS).where("teacher_id", "==", teacher_id).limit(1).stream())
        if not q:
            return []
        doc = q[0]
    t = doc.to_dict() or {}
    assignments = _teacher_assignments(t)
    seen = set()
    sections = []
    for a in assignments:
        sem = _norm_semester(a.get("semester"))
        sec = _norm_section(a.get("section"))
        code = (a.get("subject_code") or "").strip().upper()
        name = (a.get("subject_name") or "").strip()
        key = f"{sem}_{sec}_{code}"
        if not sem or not sec or not code:
            continue
        if key in seen:
            continue
        seen.add(key)
        sections.append({
            "id": f"SEM{sem}_{sec}",
            "section_name": f"Section {sec}",
            "semester": f"Semester {sem}",
            "subject": f"{code} — {name}" if name else code,
        })
    return sections


@auth_bp.route("/teacher-sections/<teacher_id>", methods=["GET"])
def teacher_sections(teacher_id):
    """Dedicated endpoint returning only the teacher's section list."""
    sections = _get_teacher_sections(teacher_id)
    return jsonify(sections)


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
        sections = _get_teacher_sections(doc.id)
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
                "sections": sections,
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
