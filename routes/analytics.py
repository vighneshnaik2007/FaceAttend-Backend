from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import math

from flask import Blueprint, jsonify

from firebase_config import ATTENDANCE, STUDENTS, SUBJECTS, db

analytics_bp = Blueprint("analytics", __name__)


def _subject_names() -> dict[str, str]:
    return {doc.id: (doc.to_dict() or {}).get("name", doc.id) for doc in db.collection(SUBJECTS).stream()}


def _week_windows() -> list[tuple[str, date, date]]:
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    windows = []
    for offset in range(3, -1, -1):
        start = current_monday - timedelta(weeks=offset)
        end = start + timedelta(days=6)
        windows.append((f"{start.strftime('%d %b')}", start, end))
    return windows


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def attendance_prediction(attended: int, total_classes: int, subject_name: str = "this subject") -> dict:
    pct = round((attended / total_classes) * 100, 1) if total_classes else 0.0
    if total_classes <= 0:
        return {
            "current_pct": pct,
            "status": "no_data",
            "classes_needed": 0,
            "message": f"No attendance records are available for {subject_name} yet.",
        }

    if pct < 75:
        classes_needed = max(0, math.ceil(((0.75 * total_classes) - attended) / 0.25))
        return {
            "current_pct": pct,
            "status": "below_75",
            "classes_needed": classes_needed,
            "message": f"You need to attend the next {classes_needed} consecutive classes without absence to reach 75% in {subject_name}.",
        }

    classes_can_miss = max(0, math.floor((attended - (0.75 * total_classes)) / 0.75))
    return {
        "current_pct": pct,
        "status": "safe" if pct > 80 else "caution",
        "classes_can_miss": classes_can_miss,
        "message": f"You can miss up to {classes_can_miss} more classes in {subject_name} and still maintain 75%.",
    }


@analytics_bp.route("/prediction/<usn>/<subject_code>", methods=["GET"])
def prediction(usn, subject_code):
    usn = (usn or "").strip().upper()
    subject_code = (subject_code or "").strip().upper()
    subject_name = _subject_names().get(subject_code, subject_code)

    attended = 0
    total_classes = 0
    for doc in db.collection(ATTENDANCE).where("usn", "==", usn).where("subject_code", "==", subject_code).stream():
        data = doc.to_dict() or {}
        total_classes += 1
        if data.get("status") == "present":
            attended += 1

    result = attendance_prediction(attended, total_classes, subject_name)
    return jsonify(result)


@analytics_bp.route("/teacher/<subject_code>", methods=["GET"])
def teacher_analytics(subject_code):
    subject_code = (subject_code or "").strip().upper()
    students = []
    student_names: dict[str, str] = {}
    for doc in db.collection(STUDENTS).order_by("usn").stream():
        data = doc.to_dict() or {}
        usn = (data.get("usn") or doc.id).upper()
        name = data.get("name") or usn
        student_names[usn] = name
        students.append({"usn": usn, "name": name, "present": 0, "total": 0})

    by_usn = {s["usn"]: s for s in students}
    weekly_counts = [{"week": label, "present": 0, "total": 0} for label, _, _ in _week_windows()]

    for doc in db.collection(ATTENDANCE).where("subject_code", "==", subject_code).stream():
        data = doc.to_dict() or {}
        usn = (data.get("usn") or "").upper()
        status = data.get("status")
        if usn in by_usn:
            by_usn[usn]["total"] += 1
            if status == "present":
                by_usn[usn]["present"] += 1

        att_date = _parse_date(data.get("date"))
        if att_date:
            for idx, (_, start, end) in enumerate(_week_windows()):
                if start <= att_date <= end:
                    weekly_counts[idx]["total"] += 1
                    if status == "present":
                        weekly_counts[idx]["present"] += 1
                    break

    student_percentages = []
    for row in students:
        total = row["total"]
        pct = round((row["present"] / total) * 100, 1) if total else 0.0
        student_percentages.append({
            "usn": row["usn"],
            "name": row["name"],
            "present": row["present"],
            "total": total,
            "percentage": pct,
        })

    weekly = []
    for row in weekly_counts:
        pct = round((row["present"] / row["total"]) * 100, 1) if row["total"] else 0.0
        weekly.append({"week": row["week"], "average": pct})

    total_students = len(student_percentages)
    average = round(
        sum(row["percentage"] for row in student_percentages) / total_students,
        1,
    ) if total_students else 0.0
    below_75 = sum(1 for row in student_percentages if row["percentage"] < 75)
    above_90 = sum(1 for row in student_percentages if row["percentage"] >= 90)

    return jsonify({
        "subject_code": subject_code,
        "subject_name": _subject_names().get(subject_code, subject_code),
        "students": student_percentages,
        "weekly": weekly,
        "ratio": [
            {"name": "Regular", "value": total_students - below_75},
            {"name": "Shortage", "value": below_75},
        ],
        "summary": {
            "totalStudents": total_students,
            "averageAttendance": average,
            "below75": below_75,
            "above90": above_90,
        },
    })


@analytics_bp.route("/student/<usn>", methods=["GET"])
def student_analytics(usn):
    usn = (usn or "").strip().upper()
    subject_names = _subject_names()
    subjects: dict[str, dict] = defaultdict(lambda: {"present": 0, "total": 0})
    weekly_by_subject: dict[str, list[dict]] = {}

    for doc in db.collection(ATTENDANCE).where("usn", "==", usn).stream():
        data = doc.to_dict() or {}
        code = (data.get("subject_code") or "").upper()
        if not code:
            continue
        status = data.get("status")
        subjects[code]["total"] += 1
        if status == "present":
            subjects[code]["present"] += 1

        weekly_by_subject.setdefault(
            code,
            [{"week": label, "present": 0, "total": 0} for label, _, _ in _week_windows()],
        )
        att_date = _parse_date(data.get("date"))
        if att_date:
            for idx, (_, start, end) in enumerate(_week_windows()):
                if start <= att_date <= end:
                    weekly_by_subject[code][idx]["total"] += 1
                    if status == "present":
                        weekly_by_subject[code][idx]["present"] += 1
                    break

    subject_rows = []
    prediction_rows = []
    for code in sorted(subjects):
        present = subjects[code]["present"]
        total = subjects[code]["total"]
        pct = round((present / total) * 100, 1) if total else 0.0
        needed = max(0, math.ceil(((0.75 * total) - present) / 0.25)) if pct < 75 else 0
        subject_rows.append({
            "subjectCode": code,
            "subjectName": subject_names.get(code, code),
            "present": present,
            "totalClasses": total,
            "percentage": pct,
        })
        prediction_rows.append({
            "subjectCode": code,
            "subjectName": subject_names.get(code, code),
            "needed": needed,
            "percentage": pct,
        })

    weekly = []
    for code, rows in sorted(weekly_by_subject.items()):
        for row in rows:
            pct = round((row["present"] / row["total"]) * 100, 1) if row["total"] else 0.0
            weekly.append({
                "subjectCode": code,
                "subjectName": subject_names.get(code, code),
                "week": row["week"],
                "percentage": pct,
            })

    return jsonify({
        "usn": usn,
        "subjects": subject_rows,
        "weekly": weekly,
        "predictions": prediction_rows,
    })
