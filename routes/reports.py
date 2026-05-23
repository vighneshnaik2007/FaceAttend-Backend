"""
routes/reports.py  —  Firestore backend
GET /api/reports/subjects    — list all subjects
GET /api/reports/timetable   — weekly timetable
GET /api/reports/daily       — daily report (bonus)
GET /api/reports/monthly     — monthly chart (bonus)
"""

from datetime import date
from flask import Blueprint, request, jsonify
from firebase_config import db, SUBJECTS, TIMETABLE, ATTENDANCE, STUDENTS

reports_bp = Blueprint("reports", __name__)

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


# ── Subjects ──────────────────────────────────────────────────────────────────
@reports_bp.route("/subjects", methods=["GET"])
def get_subjects():
    docs = db.collection(SUBJECTS).stream()
    return jsonify([{
        "code":         doc.id,
        "name":         doc.to_dict().get("name", ""),
        "shortName":    doc.to_dict().get("short_name", ""),
        "contactHours": doc.to_dict().get("contact_hours", 0),
        "color":        doc.to_dict().get("color", "#2563EB"),
        "teacher_id":   doc.to_dict().get("teacher_id", ""),
    } for doc in docs])


# ── Timetable ─────────────────────────────────────────────────────────────────
@reports_bp.route("/timetable", methods=["GET"])
def get_timetable():
    docs: dict = {d: [] for d in DAY_ORDER}
    for doc in db.collection(TIMETABLE).stream():
        d = doc.to_dict()
        day = d.get("day")
        if day in docs:
            docs[day].append({
                "subject":   d.get("subject_code"),
                "startTime": d.get("start_time"),
                "endTime":   d.get("end_time"),
                "type":      d.get("slot_type", "lecture"),
            })

    # Sort each day's slots by start_time and return ordered list
    result = []
    for day in DAY_ORDER:
        slots = sorted(docs[day], key=lambda s: s["startTime"])
        if slots:
            result.append({"day": day, "slots": slots})
    return jsonify(result)


# ── Daily report (bonus) ──────────────────────────────────────────────────────
@reports_bp.route("/daily", methods=["GET"])
def daily_report():
    subject_code = request.args.get("subject_code", "")
    report_date  = request.args.get("date", date.today().isoformat())

    att_docs     = db.collection(ATTENDANCE).where("subject_code", "==", subject_code).where("date", "==", report_date).stream()
    present_usns = {d.to_dict()["usn"] for d in att_docs if d.to_dict().get("status") == "present"}

    all_students = list(db.collection(STUDENTS).order_by("usn").stream())
    result = [{"usn": s.to_dict()["usn"], "name": s.to_dict()["name"],
               "status": "present" if s.to_dict()["usn"] in present_usns else "absent"}
              for s in all_students]

    return jsonify({
        "date": report_date, "subject_code": subject_code,
        "records": result, "present_count": len(present_usns),
        "absent_count": len(all_students) - len(present_usns),
        "total": len(all_students),
    })


# ── Monthly report (bonus) ────────────────────────────────────────────────────
@reports_bp.route("/monthly", methods=["GET"])
def monthly_report():
    subject_code = request.args.get("subject_code", "")
    year         = request.args.get("year",  str(date.today().year))
    month        = request.args.get("month", f"{date.today().month:02d}").zfill(2)
    prefix       = f"{year}-{month}"

    att_docs = db.collection(ATTENDANCE).where("subject_code", "==", subject_code).stream()
    date_map: dict = {}
    for doc in att_docs:
        d = doc.to_dict()
        if d.get("date", "").startswith(prefix):
            dt = d["date"]
            if dt not in date_map:
                date_map[dt] = {"present": 0, "absent": 0}
            if d.get("status") == "present":
                date_map[dt]["present"] += 1
            else:
                date_map[dt]["absent"] += 1

    return jsonify([{"date": dt, "present": v["present"], "absent": v["absent"]}
                    for dt, v in sorted(date_map.items())])
