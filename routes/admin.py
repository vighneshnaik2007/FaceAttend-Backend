"""
routes/admin.py  —  Admin CRUD for teachers and students
"""

from datetime import datetime

from flask import Blueprint, jsonify, request

from firebase_config import (
    ATTENDANCE,
    FACE_ENCODINGS,
    MARKS,
    NOTIFICATIONS,
    SECTIONS,
    STUDENTS,
    SUBJECTS,
    TEACHERS,
    db,
)

from services.student_face_register import store_face_encoding_for_usn
from routes.activity_log import log_admin_activity

admin_bp = Blueprint("admin", __name__)


def _norm_semester(value) -> str:
    text = str(value or "").strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _norm_section(value) -> str:
    return str(value or "").strip().upper()


def _section_id(semester, section_name: str) -> str:
    return f"SEM{_norm_semester(semester)}_{_norm_section(section_name)}"


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


def _teacher_in_section(t: dict, semester: str, section: str) -> bool:
    for assignment in _teacher_assignments(t):
        if (
            _norm_semester(assignment.get("semester")) == semester
            and _norm_section(assignment.get("section")) == section
        ):
            return True
    return False


def _student_in_section(s: dict, semester: str, section: str) -> bool:
    return _norm_semester(s.get("semester")) == semester and _norm_section(s.get("section")) == section


def _delete_collection_where(collection: str, field: str, value: str) -> int:
    count = 0
    while True:
        docs = list(db.collection(collection).where(field, "==", value).limit(200).stream())
        if not docs:
            break
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
        batch.commit()
    return count


def _delete_attendance_for_usn(usn: str) -> int:
    return _delete_collection_where(ATTENDANCE, "usn", usn.upper())


def _delete_marks_for_usn(usn: str) -> int:
    count = 0
    prefix = usn.upper() + "_"
    for doc in db.collection(MARKS).stream():
        if doc.id.startswith(prefix) or doc.to_dict().get("usn") == usn.upper():
            doc.reference.delete()
            count += 1
    return count


# ── Stats (public counts for homepage) ────────────────────────────────────────
@admin_bp.route("/stats", methods=["GET"])
def admin_stats():
    teachers = sum(1 for _ in db.collection(TEACHERS).stream())
    students = sum(1 for _ in db.collection(STUDENTS).stream())
    subjects = sum(1 for _ in db.collection(SUBJECTS).stream())
    return jsonify({
        "teachers": teachers,
        "students": students,
        "subjects": subjects,
    })


@admin_bp.route("/dashboard", methods=["GET"])
def admin_dashboard():
    teachers = sum(1 for _ in db.collection(TEACHERS).stream())
    students = sum(1 for _ in db.collection(STUDENTS).stream())
    recent = []
    for doc in list(db.collection(NOTIFICATIONS).limit(20).stream()):
        d = doc.to_dict()
        recent.append({
            "id": doc.id,
            "type": d.get("type", "info"),
            "message": d.get("message") or d.get("title", ""),
            "timestamp": d.get("timestamp", ""),
        })
    return jsonify({
        "teachers": teachers,
        "students": students,
        "recentActivity": recent,
    })


# ── Semesters & sections ─────────────────────────────────────────────────────
@admin_bp.route("/semesters-summary", methods=["GET"])
def semesters_summary():
    out = []
    for sem in range(1, 9):
        semester = str(sem)
        section_count = 0
        for doc in db.collection(SECTIONS).stream():
            if _norm_semester((doc.to_dict() or {}).get("semester")) == semester:
                section_count += 1

        student_count = 0
        for doc in db.collection(STUDENTS).stream():
            if _norm_semester((doc.to_dict() or {}).get("semester")) == semester:
                student_count += 1

        out.append({
            "semester": sem,
            "sections": section_count,
            "students": student_count,
        })
    return jsonify(out)


@admin_bp.route("/sections", methods=["GET", "POST"])
def sections():
    if request.method == "GET":
        semester = _norm_semester(request.args.get("semester"))
        if not semester:
            sections = sorted({
                _norm_section((doc.to_dict() or {}).get("section"))
                for doc in db.collection(STUDENTS).stream()
                if _norm_section((doc.to_dict() or {}).get("section"))
            })
            return jsonify(sections)

        rows = []
        for doc in db.collection(SECTIONS).stream():
            d = doc.to_dict() or {}
            if semester and _norm_semester(d.get("semester")) != semester:
                continue
            sem = _norm_semester(d.get("semester"))
            section = _norm_section(d.get("section_name"))
            student_count = sum(
                1 for sdoc in db.collection(STUDENTS).stream()
                if _student_in_section(sdoc.to_dict() or {}, sem, section)
            )
            teacher_count = sum(
                1 for tdoc in db.collection(TEACHERS).stream()
                if _teacher_in_section(tdoc.to_dict() or {}, sem, section)
            )
            rows.append({
                "id": doc.id,
                "semester": int(sem) if sem.isdigit() else sem,
                "section_name": section,
                "created_at": d.get("created_at", ""),
                "student_count": student_count,
                "teacher_count": teacher_count,
                "is_empty": student_count == 0 and teacher_count == 0,
            })
        rows.sort(key=lambda x: str(x["section_name"]))
        return jsonify(rows)

    data = request.json or {}
    semester = _norm_semester(data.get("semester"))
    section = _norm_section(data.get("section_name"))
    if not semester or not section:
        return jsonify({"success": False, "message": "semester and section_name are required"}), 400
    if not semester.isdigit() or int(semester) < 1 or int(semester) > 8:
        return jsonify({"success": False, "message": "semester must be between 1 and 8"}), 400

    doc_id = _section_id(semester, section)
    ref = db.collection(SECTIONS).document(doc_id)
    if ref.get().exists:
        return jsonify({"success": False, "message": "Section already exists for this semester"}), 409

    row = {
        "id": doc_id,
        "semester": int(semester),
        "section_name": section,
        "created_at": datetime.utcnow().isoformat(),
    }
    ref.set(row)
    return jsonify({"success": True, "section": {**row, "student_count": 0, "teacher_count": 0, "is_empty": True}})


@admin_bp.route("/sections/<semester>/<section_name>", methods=["DELETE"])
def delete_section(semester, section_name):
    semester = _norm_semester(semester)
    section = _norm_section(section_name)
    if not semester or not section:
        return jsonify({"success": False, "message": "semester and section_name are required"}), 400

    student_count = sum(
        1 for doc in db.collection(STUDENTS).stream()
        if _student_in_section(doc.to_dict() or {}, semester, section)
    )
    teacher_count = sum(
        1 for doc in db.collection(TEACHERS).stream()
        if _teacher_in_section(doc.to_dict() or {}, semester, section)
    )
    if student_count or teacher_count:
        return jsonify({"success": False, "message": "Section has assigned students or teachers"}), 409

    ref = db.collection(SECTIONS).document(_section_id(semester, section))
    if not ref.get().exists:
        return jsonify({"success": False, "message": "Section not found"}), 404
    ref.delete()
    return jsonify({"success": True})


# ── Teachers ──────────────────────────────────────────────────────────────────
@admin_bp.route("/teachers", methods=["GET", "POST"])
def list_teachers():
    if request.method == "POST":
        return _save_teacher()

    semester = _norm_semester(request.args.get("semester"))
    section = _norm_section(request.args.get("section"))
    rows = []
    for doc in db.collection(TEACHERS).stream():
        t = doc.to_dict()
        assignments = _teacher_assignments(t)
        if semester and section:
            assignments = [
                a for a in assignments
                if _norm_semester(a.get("semester")) == semester and _norm_section(a.get("section")) == section
            ]
            if not assignments:
                continue
        primary = assignments[0] if assignments else {}
        rows.append({
            "teacher_id": doc.id,
            "name": t.get("name", ""),
            "email": t.get("email", ""),
            "subject_code": primary.get("subject_code", t.get("subject_code", "")),
            "subject_name": primary.get("subject_name", t.get("subject_name", "")),
            "department": primary.get("department", t.get("department", "")),
            "semester": primary.get("semester", t.get("semester", "")),
            "section": primary.get("section", t.get("section", "")),
            "assignments": assignments,
        })
    rows.sort(key=lambda x: x["teacher_id"])
    return jsonify(rows)


@admin_bp.route("/add-teacher", methods=["POST"])
def add_teacher():
    return _save_teacher()


def _save_teacher():
    data = request.json or {}
    teacher_id = (data.get("teacher_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    subject_code = (data.get("subject_code") or "").strip().upper()
    semester = _norm_semester(data.get("semester"))
    section = _norm_section(data.get("section"))
    assignment = {
        "semester": semester,
        "section": section,
        "subject_code": subject_code,
        "subject_name": data.get("subject_name", ""),
        "department": data.get("department", ""),
    }

    if not email:
        return jsonify({"success": False, "message": "email is required"}), 400

    existing = list(db.collection(TEACHERS).where("email", "==", email).limit(1).stream())
    if email and existing:
        doc = existing[0]
        t = doc.to_dict() or {}
        assignments = _teacher_assignments(t)
        duplicate = any(
            _norm_semester(a.get("semester")) == semester
            and _norm_section(a.get("section")) == section
            and (a.get("subject_code") or "") == subject_code
            for a in assignments
        )
        if not duplicate:
            assignments.append(assignment)
        doc.reference.update({
            "assignments": assignments,
            "semester": semester or t.get("semester", ""),
            "section": section or t.get("section", ""),
            "subject_code": subject_code or t.get("subject_code", ""),
            "subject_name": data.get("subject_name", t.get("subject_name", "")),
            "department": data.get("department", t.get("department", "")),
        })
        if subject_code:
            db.collection(SUBJECTS).document(subject_code).set({
                "code": subject_code,
                "name": data.get("subject_name", subject_code),
                "teacher_id": doc.id,
                "department": data.get("department", ""),
                "semester": semester,
                "section": section,
            }, merge=True)
        log_admin_activity("teacher_added", data.get("name", ""), doc.id, f"Added teacher {data.get('name', '')} with ID {doc.id}")
        return jsonify({"success": True, "teacher_id": doc.id, "existing": True})

    if not teacher_id:
        return jsonify({"success": False, "message": "teacher_id is required"}), 400

    if db.collection(TEACHERS).document(teacher_id).get().exists:
        return jsonify({"success": False, "message": "Teacher ID already exists"}), 409

    teacher = {
        "teacher_id": teacher_id,
        "name": data.get("name", ""),
        "email": email,
        "password": data.get("password", ""),
        "subject_code": subject_code,
        "subject_name": data.get("subject_name", ""),
        "department": data.get("department", ""),
        "semester": semester,
        "section": section,
        "assignments": [assignment] if (semester or section or subject_code) else [],
    }
    db.collection(TEACHERS).document(teacher_id).set(teacher)

    if subject_code:
        db.collection(SUBJECTS).document(subject_code).set({
            "code": subject_code,
            "name": data.get("subject_name", subject_code),
            "teacher_id": teacher_id,
            "department": data.get("department", ""),
            "semester": semester,
            "section": section,
        })

    log_admin_activity("teacher_added", data.get("name", ""), teacher_id, f"Added teacher {data.get('name', '')} with ID {teacher_id}")
    return jsonify({"success": True, "teacher_id": teacher_id})


@admin_bp.route("/delete-teacher/<teacher_id>", methods=["DELETE"])
def delete_teacher(teacher_id):
    ref = db.collection(TEACHERS).document(teacher_id)
    if not ref.get().exists:
        return jsonify({"success": False, "message": "Teacher not found"}), 404
    t = ref.get().to_dict()
    subject_code = t.get("subject_code", "")
    teacher_name = t.get("name", "")
    ref.delete()
    if subject_code:
        db.collection(SUBJECTS).document(subject_code).delete()
    log_admin_activity("teacher_deleted", teacher_name, teacher_id, f"Deleted teacher {teacher_name} with ID {teacher_id}")
    return jsonify({"success": True})


@admin_bp.route("/edit-teacher/<teacher_id>", methods=["PUT"])
def edit_teacher(teacher_id):
    data = request.json or {}
    ref = db.collection(TEACHERS).document(teacher_id)
    if not ref.get().exists:
        return jsonify({"success": False, "message": "Teacher not found"}), 404

    t_original = ref.get().to_dict() or {}
    teacher_name = t_original.get("name", "")
    
    updates = {}
    for field in ("name", "email", "password", "subject_code", "subject_name", "department", "semester", "section"):
        if field in data:
            val = data[field]
            if field == "email":
                val = str(val).strip().lower()
            if field == "subject_code":
                val = str(val).strip().upper()
            if field == "semester":
                val = _norm_semester(val)
            if field == "section":
                val = _norm_section(val)
            updates[field] = val

    if updates:
        next_doc = {**t_original, **updates}
        updates["assignments"] = [{
            "semester": _norm_semester(next_doc.get("semester")),
            "section": _norm_section(next_doc.get("section")),
            "subject_code": next_doc.get("subject_code", ""),
            "subject_name": next_doc.get("subject_name", ""),
            "department": next_doc.get("department", ""),
        }]
        ref.update(updates)

    t = ref.get().to_dict()
    code = t.get("subject_code", "")
    if code:
        db.collection(SUBJECTS).document(code).set({
            "code": code,
            "name": t.get("subject_name", code),
            "teacher_id": teacher_id,
            "department": t.get("department", ""),
            "semester": t.get("semester", ""),
            "section": t.get("section", ""),
        }, merge=True)

    log_admin_activity("teacher_edited", teacher_name, teacher_id, f"Edited teacher {teacher_name} with ID {teacher_id}")
    return jsonify({"success": True})


# ── Students ──────────────────────────────────────────────────────────────────
@admin_bp.route("/students", methods=["GET", "POST"])
def list_students():
    if request.method == "POST":
        return _save_student()

    semester = _norm_semester(request.args.get("semester"))
    section = _norm_section(request.args.get("section"))
    rows = []
    for doc in db.collection(STUDENTS).stream():
        s = doc.to_dict()
        if semester and _norm_semester(s.get("semester")) != semester:
            continue
        if section and _norm_section(s.get("section")) != section:
            continue
        rows.append({
            "usn": s.get("usn", doc.id),
            "name": s.get("name", ""),
            "email": s.get("email", ""),
            "phone": s.get("phone", ""),
            "branch": s.get("branch", s.get("department", "")),
            "semester": s.get("semester", ""),
            "section": s.get("section", ""),
            "face_registered": bool(s.get("face_registered")),
        })
    rows.sort(key=lambda x: x["usn"])
    return jsonify(rows)


@admin_bp.route("/add-student", methods=["POST"])
def add_student():
    return _save_student()


def _save_student():
    data = request.json or {}
    usn = (data.get("usn") or "").strip().upper()
    if not usn:
        return jsonify({"success": False, "message": "usn is required"}), 400

    if db.collection(STUDENTS).document(usn).get().exists:
        return jsonify({"success": False, "message": "USN already exists"}), 409

    student = {
        "usn": usn,
        "name": data.get("name", ""),
        "email": (data.get("email") or "").strip().lower(),
        "password": data.get("password", ""),
        "phone": data.get("phone", ""),
        "branch": data.get("branch", ""),
        "semester": _norm_semester(data.get("semester")),
        "section": _norm_section(data.get("section")),
        "face_registered": False,
        "face_encoding": None,
    }
    db.collection(STUDENTS).document(usn).set(student)

    image_data = (data.get("image_data") or "").strip()
    resp: dict = {"success": True, "usn": usn}
    if image_data:
        ok, msg = store_face_encoding_for_usn(usn, image_data)
        resp["face_registered"] = ok
        resp["face_message"] = msg
    
    log_admin_activity("student_added", data.get("name", ""), usn, f"Added student {data.get('name', '')} with USN {usn}")
    return jsonify(resp)


@admin_bp.route("/delete-student/<usn>", methods=["DELETE"])
def delete_student(usn):
    usn = usn.upper()
    ref = db.collection(STUDENTS).document(usn)
    if not ref.get().exists:
        q = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
        if not q:
            return jsonify({"success": False, "message": "Student not found"}), 404
        ref = q[0].reference

    student_data = ref.get().to_dict() or {}
    student_name = student_data.get("name", "")
    
    ref.delete()
    db.collection(FACE_ENCODINGS).document(usn).delete()
    _delete_attendance_for_usn(usn)
    _delete_marks_for_usn(usn)

    log_admin_activity("student_deleted", student_name, usn, f"Deleted student {student_name} with USN {usn}")
    return jsonify({"success": True})


@admin_bp.route("/edit-student/<usn>", methods=["PUT"])
def edit_student(usn):
    usn = usn.upper()
    data = request.json or {}
    ref = db.collection(STUDENTS).document(usn)
    if not ref.get().exists:
        q = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
        if not q:
            return jsonify({"success": False, "message": "Student not found"}), 404
        ref = q[0].reference

    student_data = ref.get().to_dict() or {}
    student_name = student_data.get("name", "")
    
    updates = {}
    for field in ("name", "email", "password", "phone", "branch", "semester", "section"):
        if field in data:
            val = data[field]
            if field == "email":
                val = str(val).strip().lower()
            if field == "semester":
                val = _norm_semester(val)
            if field == "section":
                val = _norm_section(val)
            updates[field] = val

    if updates:
        ref.update(updates)

    image_data = (data.get("image_data") or "").strip()
    face_registered = None
    face_message = None
    if image_data:
        ok, msg = store_face_encoding_for_usn(usn, image_data)
        face_registered = ok
        face_message = msg

    log_admin_activity("student_edited", student_name, usn, f"Edited student {student_name} with USN {usn}")
    
    out = {"success": True}
    if face_registered is not None:
        out["face_registered"] = face_registered
        out["face_message"] = face_message
    return jsonify(out)
