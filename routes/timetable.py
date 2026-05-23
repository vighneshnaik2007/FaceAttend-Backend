from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from firebase_config import SECTIONS, TIMETABLE, db

timetable_bp = Blueprint("timetable", __name__)

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
TIME_SLOTS = [
    "8:00-9:00 AM",
    "9:00-10:00 AM",
    "10:00-11:00 AM",
    "11:00-12:00 PM",
    "12:00-1:00 PM",
    "1:00-2:00 PM",
    "2:00-3:00 PM",
    "3:00-4:00 PM",
    "4:00-5:00 PM",
]


def _now() -> str:
    return datetime.utcnow().isoformat()


def _norm_day(value) -> str:
    text = str(value or "").strip()
    for day in DAYS:
        if day.lower() == text.lower():
            return day
    return text


def _time_key(value: str) -> int:
    try:
        return TIME_SLOTS.index(value)
    except ValueError:
        return len(TIME_SLOTS)


def _entry_from_doc(doc) -> dict:
    data = doc.to_dict() or {}
    room_number = data.get("room_number") or data.get("room") or ""
    section_id = data.get("section_id") or data.get("section") or ""
    section_name = data.get("section_name") or data.get("section") or ""
    entry = {
        "id": doc.id,
        "section_id": section_id,
        "section_name": section_name,
        "day": _norm_day(data.get("day")),
        "time_slot": data.get("time_slot", ""),
        "subject_name": data.get("subject_name", ""),
        "teacher_id": data.get("teacher_id", ""),
        "teacher_name": data.get("teacher_name", ""),
        "room_number": room_number,
        "is_holiday": bool(data.get("is_holiday", False)),
        "holiday_reason": data.get("holiday_reason", ""),
        "created_at": data.get("created_at", ""),
        "updated_at": data.get("updated_at", ""),
    }
    entry["section"] = section_name or section_id
    entry["room"] = room_number
    return entry


def _sort_entries(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda row: (
            DAYS.index(row["day"]) if row.get("day") in DAYS else 99,
            _time_key(row.get("time_slot", "")),
            row.get("section_name", ""),
        ),
    )


def _group_by_day(entries: list[dict]) -> dict[str, list[dict]]:
    grouped = {day: [] for day in DAYS}
    for entry in _sort_entries(entries):
        if entry.get("day") in grouped:
            grouped[entry["day"]].append(entry)
    return grouped


def _section_label(data: dict, fallback_id: str) -> str:
    semester = data.get("semester", "")
    section_name = data.get("section_name") or data.get("section") or fallback_id
    return f"{semester} SEM - Section {section_name}" if semester else str(section_name)


@timetable_bp.route("/sections", methods=["GET"])
def get_sections():
    sections = []
    for doc in db.collection(SECTIONS).stream():
        data = doc.to_dict() or {}
        section_name = data.get("section_name") or data.get("section") or doc.id
        sections.append(
            {
                "id": doc.id,
                "section_id": doc.id,
                "section_name": section_name,
                "semester": data.get("semester", ""),
                "label": _section_label(data, doc.id),
            }
        )
    sections.sort(key=lambda row: (str(row.get("semester", "")), str(row.get("section_name", ""))))
    return jsonify({"success": True, "sections": sections})


@timetable_bp.route("/entry", methods=["POST"])
def create_entry():
    data = request.json or {}
    required = [
        "section_id",
        "section_name",
        "day",
        "time_slot",
        "subject_name",
        "teacher_id",
        "teacher_name",
        "room_number",
    ]
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return jsonify({"success": False, "message": f"Missing fields: {', '.join(missing)}"}), 400

    day = _norm_day(data.get("day"))
    if day not in DAYS:
        return jsonify({"success": False, "message": "day must be Monday through Saturday"}), 400

    entry = {
        "section_id": str(data.get("section_id")).strip(),
        "section_name": str(data.get("section_name")).strip(),
        "day": day,
        "time_slot": str(data.get("time_slot")).strip(),
        "subject_name": str(data.get("subject_name")).strip(),
        "teacher_id": str(data.get("teacher_id")).strip(),
        "teacher_name": str(data.get("teacher_name")).strip(),
        "room_number": str(data.get("room_number")).strip(),
        "is_holiday": bool(data.get("is_holiday", False)),
        "holiday_reason": str(data.get("holiday_reason", "")).strip(),
        "created_at": _now(),
        "updated_at": _now(),
    }
    doc_ref = db.collection(TIMETABLE).add(entry)[1]
    return jsonify({"success": True, "entry": {"id": doc_ref.id, **entry, "room": entry["room_number"], "section": entry["section_name"]}}), 201


@timetable_bp.route("/section/<section_id>", methods=["GET"])
def get_section_timetable(section_id):
    entries = [_entry_from_doc(doc) for doc in db.collection(TIMETABLE).where("section_id", "==", section_id).stream()]
    if not entries:
        entries = [_entry_from_doc(doc) for doc in db.collection(TIMETABLE).where("section_name", "==", section_id).stream()]
    return jsonify({"success": True, "section_id": section_id, "entries": _sort_entries(entries), "days": _group_by_day(entries)})


@timetable_bp.route("/teacher/<teacher_id>", methods=["GET"])
def get_teacher_timetable(teacher_id):
    entries = [_entry_from_doc(doc) for doc in db.collection(TIMETABLE).where("teacher_id", "==", teacher_id).stream()]
    return jsonify({"success": True, "teacher_id": teacher_id, "entries": _sort_entries(entries), "days": _group_by_day(entries)})


@timetable_bp.route("/entry/<entry_id>", methods=["PUT"])
def update_entry(entry_id):
    ref = db.collection(TIMETABLE).document(entry_id)
    if not ref.get().exists:
        return jsonify({"success": False, "message": "Timetable entry not found"}), 404

    data = request.json or {}
    allowed = {
        "section_id",
        "section_name",
        "day",
        "time_slot",
        "subject_name",
        "teacher_id",
        "teacher_name",
        "room_number",
        "is_holiday",
        "holiday_reason",
    }
    updates = {key: data[key] for key in allowed if key in data}
    if "day" in updates:
        updates["day"] = _norm_day(updates["day"])
        if updates["day"] not in DAYS:
            return jsonify({"success": False, "message": "day must be Monday through Saturday"}), 400
    if "room" in data and "room_number" not in updates:
        updates["room_number"] = data["room"]
    updates["updated_at"] = _now()
    ref.update(updates)
    return jsonify({"success": True, "entry": _entry_from_doc(ref.get())})


@timetable_bp.route("/entry/<entry_id>", methods=["DELETE"])
def delete_entry(entry_id):
    ref = db.collection(TIMETABLE).document(entry_id)
    if not ref.get().exists:
        return jsonify({"success": False, "message": "Timetable entry not found"}), 404
    ref.delete()
    return jsonify({"success": True})


@timetable_bp.route("/holiday/<entry_id>", methods=["PUT"])
def mark_holiday(entry_id):
    ref = db.collection(TIMETABLE).document(entry_id)
    if not ref.get().exists:
        return jsonify({"success": False, "message": "Timetable entry not found"}), 404
    data = request.json or {}
    ref.update(
        {
            "is_holiday": True,
            "holiday_reason": str(data.get("reason") or data.get("holiday_reason") or "").strip(),
            "updated_at": _now(),
        }
    )
    return jsonify({"success": True, "entry": _entry_from_doc(ref.get())})
