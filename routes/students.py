"""
routes/students.py
──────────────────
GET    /api/students/         — list all students
POST   /api/students/         — add a new student
GET    /api/students/<usn>    — get one student + attendance %
PUT    /api/students/<usn>    — update student fields
DELETE /api/students/<usn>    — delete student
"""

import uuid
from flask import Blueprint, request, jsonify
from firebase_config import db, STUDENTS, ATTENDANCE

students_bp = Blueprint("students", __name__)


def _doc_to_student(doc_id: str, data: dict) -> dict:
    return {
        "id":             doc_id,
        "name":           data.get("name", ""),
        "usn":            data.get("usn", ""),
        "email":          data.get("email", ""),
        "phone":          data.get("phone", ""),
        "section":        data.get("section", ""),
        "semester":       data.get("semester", 2),
        "department":     data.get("department", "CSE"),
        "cgpa":           data.get("cgpa", 0.0),
        "address":        data.get("address", "Bengaluru, Karnataka"),
        "joinedDate":     data.get("joined_date", "Feb 2026"),
        "faceRegistered": bool(data.get("face_registered", False)),
    }


# ── GET all students ───────────────────────────────────────────────────────────
@students_bp.route("/", methods=["GET"])
def get_students():
    docs = db.collection(STUDENTS).order_by("usn").stream()
    return jsonify([_doc_to_student(d.id, d.to_dict()) for d in docs])


# ── GET one student ────────────────────────────────────────────────────────────
@students_bp.route("/<usn>", methods=["GET"])
def get_student(usn):
    usn = usn.upper()
    query = db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream()
    docs  = list(query)
    if not docs:
        return jsonify({"error": "Student not found"}), 404

    doc    = docs[0]
    data   = doc.to_dict()
    result = _doc_to_student(doc.id, data)

    # Compute per-subject attendance percentage
    att_docs = (
        db.collection(ATTENDANCE)
        .where("usn", "==", usn)
        .stream()
    )
    total   = 0
    present = 0
    for a in att_docs:
        total += 1
        if a.to_dict().get("status") == "present":
            present += 1

    result["attendance"] = round((present / total) * 100, 1) if total else 0.0
    return jsonify(result)


# ── POST add student ───────────────────────────────────────────────────────────
@students_bp.route("/", methods=["POST"])
def add_student():
    data = request.json or {}
    usn  = data.get("usn", "").upper()

    # Check for duplicate USN
    existing = db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream()
    if list(existing):
        return jsonify({"success": False, "message": "USN already exists"}), 409

    doc_id = str(uuid.uuid4())[:8]
    student = {
        "name":           data.get("name", ""),
        "usn":            usn,
        "email":          data.get("email", ""),
        "phone":          data.get("phone", ""),
        "section":        data.get("section", "K"),
        "semester":       data.get("semester", 2),
        "department":     data.get("department", "CSE"),
        "cgpa":           data.get("cgpa", 0.0),
        "address":        data.get("address", "Bengaluru, Karnataka"),
        "joined_date":    data.get("joinedDate", "Feb 2026"),
        "face_registered": False,
        "face_encoding":  None,
    }
    db.collection(STUDENTS).document(doc_id).set(student)
    return jsonify({"success": True, "id": doc_id})


# ── PUT update student ─────────────────────────────────────────────────────────
@students_bp.route("/<usn>", methods=["PUT"])
def update_student(usn):
    usn   = usn.upper()
    data  = request.json or {}
    query = db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream()
    docs  = list(query)
    if not docs:
        return jsonify({"error": "Student not found"}), 404

    updates = {}
    for field in ("name", "email", "phone", "cgpa", "address", "section", "semester", "department"):
        if field in data:
            updates[field] = data[field]
    if "joinedDate" in data:
        updates["joined_date"] = data["joinedDate"]

    docs[0].reference.update(updates)
    return jsonify({"success": True})


# ── DELETE student ─────────────────────────────────────────────────────────────
@students_bp.route("/<usn>", methods=["DELETE"])
def delete_student(usn):
    usn   = usn.upper()
    query = db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream()
    docs  = list(query)
    if not docs:
        return jsonify({"error": "Student not found"}), 404
    docs[0].reference.delete()
    return jsonify({"success": True})
