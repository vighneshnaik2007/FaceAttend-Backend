"""
routes/attendance.py  —  Firestore backend
"""

import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from firebase_config import ATTENDANCE, STUDENTS, SUBJECTS, NOTIFICATIONS, db
from services.notifications import send_shortage_alert, subject_attendance_stats

attendance_bp = Blueprint("attendance", __name__)
logger = logging.getLogger(__name__)


def _trigger_shortage_alerts_after_update(usn: str, subject_code: str) -> None:
    """Send external shortage alerts if computed % is below 75 (non-blocking for API errors)."""
    try:
        total_sessions, pct = subject_attendance_stats(usn, subject_code)
        if total_sessions and pct < 75:
            send_shortage_alert(usn, subject_code, pct)
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception(
            "Shortage notification hook failed for USN=%s subject=%s",
            usn,
            subject_code,
        )


def _subject_pct_map(subject_code: str) -> dict[str, float]:
    """USN -> attendance % for this subject (all class sessions counted)."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"present": 0, "absent": 0})
    for doc in db.collection(ATTENDANCE).where("subject_code", "==", subject_code).stream():
        d = doc.to_dict()
        u = d.get("usn", "")
        if not u:
            continue
        if d.get("status") == "present":
            counts[u]["present"] += 1
        else:
            counts[u]["absent"] += 1
    out: dict[str, float] = {}
    for u, c in counts.items():
        t = c["present"] + c["absent"]
        out[u] = round((c["present"] / t) * 100, 1) if t else 0.0
    return out


def _get_student_by_usn(usn: str):
    docs = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
    if not docs:
        return None, None
    return docs[0].id, docs[0].to_dict()


def _att_id(usn: str, subject_code: str, att_date: str) -> str:
    return f"{usn}_{subject_code}_{att_date}"


# ── Mark single ───────────────────────────────────────────────────────────────
@attendance_bp.route("/mark", methods=["POST"])
def mark_attendance():
    data         = request.json or {}
    usn          = data.get("usn", "").upper()
    subject_code = data.get("subject_code", "")
    status       = data.get("status", "present")
    marked_by    = data.get("marked_by", "Teacher")
    att_date     = data.get("date", date.today().isoformat())
    time_marked  = datetime.now().strftime("%I:%M %p")

    s_id, student = _get_student_by_usn(usn)
    if not student:
        return jsonify({"success": False, "message": "Student not found"}), 404

    doc_ref = db.collection(ATTENDANCE).document(_att_id(usn, subject_code, att_date))
    if doc_ref.get().exists:
        return jsonify({"success": False, "message": "Already marked for today"}), 409

    doc_ref.set({
        "student_id": s_id, "student_name": student["name"],
        "usn": usn, "subject_code": subject_code,
        "date": att_date, "status": status,
        "time_marked": time_marked, "marked_by": marked_by,
    })
    db.collection(NOTIFICATIONS).add({
        "user_id": s_id, "user_role": "student", "type": "attendance",
        "title": f"Attendance Marked — {subject_code}",
        "message": f"You are {'PRESENT' if status == 'present' else 'ABSENT'} in {subject_code}",
        "timestamp": datetime.now().strftime("%I:%M %p Today"), "read": False,
    })
    _trigger_shortage_alerts_after_update(usn, subject_code)
    return jsonify({"success": True, "message": f"{student['name']} marked {status}"})


# ── Mark bulk ─────────────────────────────────────────────────────────────────
@attendance_bp.route("/mark-bulk", methods=["POST"])
def mark_bulk():
    data         = request.json or {}
    subject_code = data.get("subject_code", "")
    att_date     = data.get("date", date.today().isoformat())
    marked_by    = data.get("marked_by", "Teacher")
    records      = data.get("records", [])

    batch = db.batch()
    count = 0
    affected_usns: set[str] = set()
    for rec in records:
        usn    = rec.get("usn", "").upper()
        status = rec.get("status", "present")
        s_id, student = _get_student_by_usn(usn)
        if not student:
            continue
        affected_usns.add(usn)
        ref = db.collection(ATTENDANCE).document(_att_id(usn, subject_code, att_date))
        batch.set(ref, {
            "student_id": s_id, "student_name": student["name"],
            "usn": usn, "subject_code": subject_code,
            "date": att_date, "status": status,
            "time_marked": datetime.now().strftime("%I:%M %p"), "marked_by": marked_by,
        })
        count += 1
    batch.commit()
    for u in affected_usns:
        _trigger_shortage_alerts_after_update(u, subject_code)
    return jsonify({"success": True, "marked": count})


# ── Today's attendance ────────────────────────────────────────────────────────
@attendance_bp.route("/today/<subject_code>", methods=["GET"])
def today_attendance(subject_code):
    today    = date.today().isoformat()
    att_docs = db.collection(ATTENDANCE).where("subject_code", "==", subject_code).where("date", "==", today).stream()
    records  = {d.to_dict()["usn"]: d.to_dict() for d in att_docs}
    present_usns = {u for u, d in records.items() if d["status"] == "present"}

    pct_by_usn = _subject_pct_map(subject_code)
    all_students = list(db.collection(STUDENTS).order_by("usn").stream())
    result = []
    for s in all_students:
        sd  = s.to_dict()
        usn = sd["usn"]
        apct = pct_by_usn.get(usn, 0.0)
        result.append({
            "usn": usn, "name": sd["name"],
            "status": "present" if usn in present_usns else "absent",
            "timeMarked": records[usn]["time_marked"] if usn in records else "-",
            "attendance_pct": apct,
        })
    return jsonify({
        "date": today,
        "subject_code": subject_code,
        "records": result,
        "present_count": len(present_usns),
        "absent_count": len(all_students) - len(present_usns),
        "total": len(all_students),
        "submitted": len(records) > 0,
    })


# ── Student attendance summary ────────────────────────────────────────────────
@attendance_bp.route("/student/<usn>", methods=["GET"])
def student_attendance(usn):
    usn      = usn.upper()
    att_docs = list(db.collection(ATTENDANCE).where("usn", "==", usn).stream())
    subj_map: dict = {}
    for doc in att_docs:
        d    = doc.to_dict()
        code = d.get("subject_code", "")
        if code not in subj_map:
            subj_map[code] = {"present": 0, "absent": 0}
        if d.get("status") == "present":
            subj_map[code]["present"] += 1
        else:
            subj_map[code]["absent"] += 1

    result = []
    for sub in db.collection(SUBJECTS).stream():
        sd      = sub.to_dict()
        code    = sub.id
        present = subj_map.get(code, {}).get("present", 0)
        absent  = subj_map.get(code, {}).get("absent", 0)
        total   = present + absent
        if total == 0:
            continue
        pct_val = round((present / total) * 100, 1)
        result.append({
            "subjectCode": code, "subjectName": sd.get("name", code),
            "totalClasses": total, "present": present, "absent": absent,
            "percentage": pct_val,
            "attendance_pct": pct_val,
        })
    return jsonify(result)


# ── History ───────────────────────────────────────────────────────────────────
@attendance_bp.route("/history/<usn>", methods=["GET"])
def attendance_history(usn):
    usn     = usn.upper()
    docs    = db.collection(ATTENDANCE).where("usn", "==", usn).order_by("date", direction="DESCENDING").limit(60).stream()
    sub_map = {d.id: d.to_dict().get("name", d.id) for d in db.collection(SUBJECTS).stream()}
    result  = []
    for doc in docs:
        d    = doc.to_dict()
        code = d.get("subject_code", "")
        result.append({
            "id": doc.id, "subjectCode": code, "subjectName": sub_map.get(code, code),
            "date": d.get("date"), "status": d.get("status"),
            "timeMarked": d.get("time_marked", "-"), "markedBy": d.get("marked_by", "Teacher"),
        })
    return jsonify(result)


# ── Defaulters ────────────────────────────────────────────────────────────────
@attendance_bp.route("/defaulters/<subject_code>", methods=["GET"])
def defaulters(subject_code):
    att_docs      = list(db.collection(ATTENDANCE).where("subject_code", "==", subject_code).stream())
    class_dates   = {d.to_dict()["date"] for d in att_docs}
    total_classes = len(class_dates) or 1
    present_map: dict = {}
    for doc in att_docs:
        d = doc.to_dict()
        if d.get("status") == "present":
            present_map[d["usn"]] = present_map.get(d["usn"], 0) + 1

    result = []
    for s in db.collection(STUDENTS).stream():
        sd      = s.to_dict()
        usn     = sd["usn"]
        present = present_map.get(usn, 0)
        pct     = round((present / total_classes) * 100, 1)
        if pct < 75:
            classes_needed = max(0, math.ceil(((0.75 * total_classes) - present) / 0.25))
            result.append({
                "name": sd["name"],
                "usn": usn,
                "attendance": pct,
                "present": present,
                "total": total_classes,
                "classes_needed": classes_needed,
            })
    return jsonify(sorted(result, key=lambda x: x["attendance"]))


# ── Weekly (bonus) ────────────────────────────────────────────────────────────
@attendance_bp.route("/weekly/<subject_code>", methods=["GET"])
def weekly_summary(subject_code):
    today  = date.today()
    result = []
    for i, label in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
        target   = (today - timedelta(days=today.weekday() - i)).isoformat()
        day_docs = list(db.collection(ATTENDANCE).where("subject_code", "==", subject_code).where("date", "==", target).stream())
        result.append({
            "day": label,
            "present": sum(1 for d in day_docs if d.to_dict().get("status") == "present"),
            "absent":  sum(1 for d in day_docs if d.to_dict().get("status") == "absent"),
        })
    return jsonify(result)


# ── By-date (bonus) ───────────────────────────────────────────────────────────
@attendance_bp.route("/by-date", methods=["GET"])
def by_date():
    subject_code = request.args.get("subject_code", "")
    att_date     = request.args.get("date", date.today().isoformat())
    docs = db.collection(ATTENDANCE).where("subject_code", "==", subject_code).where("date", "==", att_date).stream()
    return jsonify([{"usn": d.to_dict()["usn"], "name": d.to_dict()["student_name"], "status": d.to_dict()["status"], "timeMarked": d.to_dict().get("time_marked", "-")} for d in docs])


@attendance_bp.route("/today-date", methods=["GET"])
def today_date():
    return jsonify({"today": date.today().isoformat()})


@attendance_bp.route("/dates/<subject_code>", methods=["GET"])
def attendance_dates(subject_code):
    docs = db.collection(ATTENDANCE).where("subject_code", "==", subject_code).stream()
    dates = sorted({d.to_dict().get("date") for d in docs if d.to_dict().get("date")}, reverse=True)
    return jsonify({"dates": dates})


# ── Edit (bonus) ─────────────────────────────────────────────────────────────
@attendance_bp.route("/edit", methods=["POST"])
def edit_attendance():
    data    = request.json or {}
    usn     = data.get("usn", "").upper()
    code    = data.get("subject_code", "")
    dt      = data.get("date", "")
    status  = data.get("status", "present")
    doc_ref = db.collection(ATTENDANCE).document(_att_id(usn, code, dt))
    if not doc_ref.get().exists:
        return jsonify({"success": False, "message": "Record not found"}), 404
    doc_ref.update({"status": status})
    _trigger_shortage_alerts_after_update(usn, code)
    return jsonify({"success": True})
