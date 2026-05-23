"""
routes/marks.py  —  Firestore backend (no pre-loaded marks; created on first save)
"""

from flask import Blueprint, jsonify, request

from firebase_config import MARKS, STUDENTS, SUBJECTS, db

marks_bp = Blueprint("marks", __name__)


def _marks_doc_id(usn: str, subject_code: str) -> str:
    return f"{usn.upper()}_{subject_code}"


def _grade_from_percentage(pct: float) -> tuple[str, float]:
    """VTU-style letter grade and grade point from percentage."""
    if pct >= 90:
        return "O", 10.0
    if pct >= 80:
        return "A+", 9.0
    if pct >= 70:
        return "A", 8.0
    if pct >= 60:
        return "B+", 7.0
    if pct >= 55:
        return "B", 6.0
    if pct >= 50:
        return "C", 5.0
    if pct >= 40:
        return "P", 4.0
    return "F", 0.0


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
        "subjectCode": code,
        "subjectName": subject_name,
        "cie1": c1,
        "cie2": c2,
        "assignment": asg,
        "totalInternal": total_internal,
        "see": see_val,
        "totalMarks": total_marks,
        "grade": grade,
        "gradePoint": grade_point,
        "hasMarks": True,
    }


@marks_bp.route("/<subject_code>", methods=["GET"])
def get_marks(subject_code):
    """All students for a subject; marks fields are null until teacher saves."""
    students = list(db.collection(STUDENTS).order_by("usn").stream())
    result = []
    for s in students:
        sd = s.to_dict()
        usn = sd.get("usn", s.id)
        doc = db.collection(MARKS).document(_marks_doc_id(usn, subject_code)).get()
        if doc.exists:
            m = doc.to_dict()
            result.append({
                "studentId": s.id,
                "usn": usn,
                "name": sd.get("name", ""),
                "hasMarks": True,
                "cie1": m.get("cie1"),
                "cie2": m.get("cie2"),
                "cie3": m.get("cie3"),
                "assignment": m.get("assignment"),
                "see": m.get("see"),
            })
        else:
            result.append({
                "studentId": s.id,
                "usn": usn,
                "name": sd.get("name", ""),
                "hasMarks": False,
                "cie1": None,
                "cie2": None,
                "cie3": None,
                "assignment": None,
                "see": None,
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
            return jsonify({"success": False, "message": "CIE1 marks must be between 0 and 30"}), 400
        if cie2 is not None and (float(cie2) < 0 or float(cie2) > 30):
            return jsonify({"success": False, "message": "CIE2 marks must be between 0 and 30"}), 400
        if assignment is not None and (float(assignment) < 0 or float(assignment) > 20):
            return jsonify({"success": False, "message": "Assignment marks must be between 0 and 20"}), 400
        if see is not None and (float(see) < 0 or float(see) > 100):
            return jsonify({"success": False, "message": "SEE marks must be between 0 and 100"}), 400

    batch = db.batch()
    count = 0
    for rec in records:
        usn = rec.get("usn", "").upper()
        if not usn:
            continue
        ref = db.collection(MARKS).document(_marks_doc_id(usn, subject_code))
        batch.set(ref, {
            "usn": usn,
            "subject_code": subject_code,
            "cie1": rec.get("cie1"),
            "cie2": rec.get("cie2"),
            "cie3": rec.get("cie3"),
            "assignment": rec.get("assignment"),
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
        d.to_dict().get("cie1", 0) + d.to_dict().get("cie2", 0) + d.to_dict().get("cie3", 0)
        for d in docs
    ]
    return jsonify({
        "average": round(sum(totals) / len(totals), 1),
        "highest": max(totals),
        "lowest": min(totals),
        "pass": sum(1 for t in totals if t >= 25),
        "fail": sum(1 for t in totals if t < 25),
        "count": len(totals),
    })
