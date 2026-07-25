"""
routes/marks.py  —  Firestore backend (no pre-loaded marks; created on first save)
"""

from flask import Blueprint, jsonify, request

from firebase_config import MARKS, STUDENTS, SUBJECTS, TEACHERS, db

marks_bp = Blueprint("marks", __name__)


def _marks_doc_id(usn: str, subject_code: str) -> str:
    return f"{usn.upper()}_{subject_code}"


def _grade_from_percentage(pct: float) -> tuple[str, float]:
    if pct >= 90: return "O", 10.0
    if pct >= 80: return "A+", 9.0
    if pct >= 70: return "A", 8.0
    if pct >= 60: return "B+", 7.0
    if pct >= 55: return "B", 6.0
    if pct >= 50: return "C", 5.0
    if pct >= 40: return "P", 4.0
    return "F", 0.0


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
    return [{"semester": semester, "section": section,
             "subject_code": t.get("subject_code", ""),
             "subject_name": t.get("subject_name", ""),
             "department": t.get("department", "")}]


def _scope_for_subject(subject_code: str) -> tuple[str, str]:
    """Return (semester, section) for this subject by checking SUBJECTS then TEACHERS."""
    subj_doc = db.collection(SUBJECTS).document(subject_code).get()
    subj = subj_doc.to_dict() if subj_doc.exists else {}
    semester = _norm_semester(subj.get("semester"))
    section = _norm_section(subj.get("section"))
    if semester or section:
        return semester, section

    for doc in db.collection(TEACHERS).stream():
        t = doc.to_dict() or {}
        for a in _teacher_assignments(t):
            if (a.get("subject_code") or "").strip().upper() == subject_code.strip().upper():
                s = _norm_semester(a.get("semester"))
                sec = _norm_section(a.get("section"))
                if s or sec:
                    return s, sec
    return "", ""


def _students_for_subject(subject_code: str, section_override: str = ""):
    """Return students in the subject's section (or the override section)."""
    subj_semester, subj_section = _scope_for_subject(subject_code)

    # Allow caller to override section (when teacher has same subject in 2 sections)
    if section_override:
        subj_section = _norm_section(section_override)

    all_docs = list(db.collection(STUDENTS).order_by("usn").stream())
    if not subj_semester and not subj_section:
        return all_docs

    filtered = []
    for s in all_docs:
        sd = s.to_dict()
        if subj_semester and _norm_semester(sd.get("semester")) != subj_semester:
            continue
        if subj_section and _norm_section(sd.get("section")) != subj_section:
            continue
        filtered.append(s)
    return filtered


def _build_student_mark_row(code: str, subject_name: str, m: dict) -> dict:
    c1 = m.get("cie1") or 0
    c2 = m.get("cie2") or 0
    asg = m.get("assignment") or 0
    see = m.get("see")
    total_internal = round(((c1 + c2) / 2) + asg, 1)
    see_val = see if see is not None else None
    if see_val is not None:
        total_marks = round(total_internal + (see_val / 2), 1)
        pct = (total_marks / 100) * 100
    else:
        total_marks = None
        pct = (total_internal / 50) * 100 if total_internal else 0
    grade, grade_point = _grade_from_percentage(pct)
    return {
        "subjectCode": code, "subjectName": subject_name,
        "cie1": c1, "cie2": c2, "assignment": asg,
        "totalInternal": total_internal, "see": see_val,
        "totalMarks": total_marks, "grade": grade,
        "gradePoint": grade_point, "hasMarks": True,
    }


@marks_bp.route("/<subject_code>", methods=["GET"])
def get_marks(subject_code):
    """All students for a subject+section; marks fields are null until teacher saves."""
    # Optional section override from query param
    section_override = request.args.get("section", "")
    students = _students_for_subject(subject_code, section_override)
    result = []
    for s in students:
        sd = s.to_dict()
        usn = sd.get("usn", s.id)
        doc = db.collection(MARKS).document(_marks_doc_id(usn, subject_code)).get()
        if doc.exists:
            m = doc.to_dict()
            result.append({
                "studentId": s.id, "usn": usn, "name": sd.get("name", ""),
                "hasMarks": True, "cie1": m.get("cie1"), "cie2": m.get("cie2"),
                "cie3": m.get("cie3"), "assignment": m.get("assignment"), "see": m.get("see"),
            })
        else:
            result.append({
                "studentId": s.id, "usn": usn, "name": sd.get("name", ""),
                "hasMarks": False, "cie1": None, "cie2": None,
                "cie3": None, "assignment": None, "see": None,
            })
    return jsonify(result)


@marks_bp.route("/student/<usn>", methods=["GET"])
def student_marks(usn):
    usn = usn.upper()
    result = []
    grade_points: list[float] = []
    for sub in db.collection(SUBJECTS).stream():
        sd = sub.to_dict()
        code = sub.id
        doc = db.collection(MARKS).document(_marks_doc_id(usn, code)).get()
        if not doc.exists:
            continue
        row = _build_student_mark_row(code, sd.get("name", code), doc.to_dict())
        result.append(row)
        grade_points.append(row["gradePoint"])
    cgpa = round(sum(grade_points) / len(grade_points), 2) if grade_points else None
    return jsonify({"subjects": result, "cgpa": cgpa, "subjectCount": len(result)})


@marks_bp.route("/save", methods=["POST"])
def save_marks():
    data = request.json or {}
    subject_code = data.get("subject_code", "")
    records = data.get("records", [])

    for rec in records:
        cie1 = rec.get("cie1")
        cie2 = rec.get("cie2")
        assignment = rec.get("assignment")
        see = rec.get("see")
        if cie1 is not None and (float(cie1) < 0 or float(cie1) > 30):
            return jsonify({"success": False, "message": "CIE1 must be 0–30"}), 400
        if cie2 is not None and (float(cie2) < 0 or float(cie2) > 30):
            return jsonify({"success": False, "message": "CIE2 must be 0–30"}), 400
        if assignment is not None and (float(assignment) < 0 or float(assignment) > 20):
            return jsonify({"success": False, "message": "Assignment must be 0–20"}), 400
        if see is not None and (float(see) < 0 or float(see) > 100):
            return jsonify({"success": False, "message": "SEE must be 0–100"}), 400

    batch = db.batch()
    count = 0
    for rec in records:
        usn = rec.get("usn", "").upper()
        if not usn:
            continue
        ref = db.collection(MARKS).document(_marks_doc_id(usn, subject_code))
        batch.set(ref, {
            "usn": usn, "subject_code": subject_code,
            "cie1": rec.get("cie1"), "cie2": rec.get("cie2"),
            "cie3": rec.get("cie3"), "assignment": rec.get("assignment"),
            "see": rec.get("see"),
        })
        count += 1
    batch.commit()
    return jsonify({"success": True, "saved": count})


@marks_bp.route("/stats/<subject_code>", methods=["GET"])
def marks_stats(subject_code):
    docs = list(db.collection(MARKS).where("subject_code", "==", subject_code).stream())
    if not docs:
        return jsonify({"average": 0, "highest": 0, "lowest": 0, "pass": 0, "fail": 0, "count": 0})
    totals = [
        (d.to_dict().get("cie1") or 0) + (d.to_dict().get("cie2") or 0) + (d.to_dict().get("cie3") or 0)
        for d in docs
    ]
    return jsonify({
        "average": round(sum(totals) / len(totals), 1),
        "highest": max(totals), "lowest": min(totals),
        "pass": sum(1 for t in totals if t >= 25),
        "fail": sum(1 for t in totals if t < 25),
        "count": len(totals),
    })