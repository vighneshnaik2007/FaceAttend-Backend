"""
routes/face.py  —  Face registration & real-time recognition (Firestore + face_recognition)
POST /api/face/register        — store encoding in face_encodings (doc id = USN)
POST /api/face/recognize       — match faces in frame against all stored encodings
GET  /api/face/status?usn=USN — whether face is registered
GET  /api/face/status/<usn>    — whether face is registered (legacy)
GET  /api/face/health          — library availability check
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import cv2
import numpy as np
from flask import Blueprint, jsonify, request

from firebase_config import FACE_ENCODINGS, STUDENTS, db

from services.student_face_register import (
    decode_image_data_url,
    store_face_encoding_for_usn,
)

logger = logging.getLogger(__name__)

try:
    import face_recognition

    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    face_recognition = None  # type: ignore
    FACE_RECOGNITION_AVAILABLE = False

face_bp = Blueprint("face", __name__)

MATCH_TOLERANCE = 0.5
UNRECOGNIZED_MSG = "Face not recognized — please mark manually"


def _decode_image(image_data: str):
    """Decode a base64 data-URL from the frontend webcam."""
    return decode_image_data_url(image_data)


def _get_student_doc(usn: str):
    usn = (usn or "").upper()
    doc = db.collection(STUDENTS).document(usn).get()
    if doc.exists:
        return doc.id, doc.to_dict()
    docs = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
    if not docs:
        return None, None
    return docs[0].id, docs[0].to_dict()


def _parse_encoding(raw) -> np.ndarray | None:
    if not raw:
        return None
    try:
        if isinstance(raw, str):
            return np.array(json.loads(raw))
        return np.array(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _parse_encoding_list(raw) -> list[np.ndarray]:
    if not raw:
        return []
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list) and raw and isinstance(raw[0], list):
            return [np.array(item) for item in raw]
        enc = _parse_encoding(raw)
        return [enc] if enc is not None else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _encoding_from_image(image_data: str, index: int | None = None) -> tuple[np.ndarray | None, str | None, np.ndarray | None]:
    try:
        img = _decode_image(image_data)
    except ValueError as exc:
        label = f"Image {index}: " if index else ""
        return None, f"{label}{exc}", None

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model="hog")
    encodings = face_recognition.face_encodings(rgb, boxes)

    label = f"Image {index}: " if index else ""
    if not encodings:
        return None, f"{label}No face detected. Use good lighting and keep your face clearly visible.", None
    if len(encodings) > 1:
        return None, f"{label}Multiple faces detected. Only the student should be in the photo.", None
    return encodings[0], None, img


def _load_registered_encodings() -> list[tuple[str, str, list[np.ndarray]]]:
    """
    Load all face encodings from face_encodings collection (document ID = USN).
    Falls back to students.face_encoding for legacy records.
    """
    out: list[tuple[str, str, list[np.ndarray]]] = []
    seen: set[str] = set()

    for doc in db.collection(FACE_ENCODINGS).stream():
        usn = doc.id.upper()
        data = doc.to_dict() or {}
        encodings = _parse_encoding_list(data.get("face_encodings"))
        legacy = _parse_encoding(data.get("face_encoding"))
        if legacy is not None:
            encodings.append(legacy)
        if not encodings:
            continue
        _, student = _get_student_doc(usn)
        name = (student or {}).get("name") or data.get("name") or usn
        out.append((usn, name, encodings))
        seen.add(usn)

    for doc in db.collection(STUDENTS).where("face_registered", "==", True).stream():
        data = doc.to_dict() or {}
        usn = (data.get("usn") or doc.id).upper()
        if usn in seen:
            continue
        enc = _parse_encoding(data.get("face_encoding"))
        if enc is None:
            continue
        out.append((usn, data.get("name", usn), [enc]))
        seen.add(usn)

    return out


def _serialize_timestamp(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


# ── Health ────────────────────────────────────────────────────────────────────
@face_bp.route("/health", methods=["GET"])
def face_health():
    count = sum(1 for _ in db.collection(FACE_ENCODINGS).limit(500).stream())
    return jsonify({
        "available": FACE_RECOGNITION_AVAILABLE,
        "library": "face_recognition" if FACE_RECOGNITION_AVAILABLE else None,
        "opencv": True,
        "registered_faces": count,
    })


# ── Register face ─────────────────────────────────────────────────────────────
@face_bp.route("/register", methods=["POST"])
def register_face():
    if not FACE_RECOGNITION_AVAILABLE:
        return jsonify({"success": False, "message": "face_recognition library not installed"}), 500

    data = request.json or {}
    usn = (data.get("usn") or "").upper()
    images = data.get("images")
    image_data = data.get("image_data")

    if not usn:
        return jsonify({"success": False, "message": "USN is required"}), 400

    if images is not None:
        if not isinstance(images, list) or len(images) != 5:
            return jsonify({"success": False, "message": "images must be an array of exactly 5 base64 strings"}), 400

        doc_id, student = _get_student_doc(usn)
        if not student:
            return jsonify({"success": False, "message": "Student USN not found"}), 404

        encodings: list[np.ndarray] = []
        thumbnails: list[str] = []
        for index, item in enumerate(images, start=1):
            if not isinstance(item, str) or not item:
                return jsonify({"success": False, "message": f"Image {index}: base64 image is required"}), 400
            enc, error, img = _encoding_from_image(item, index)
            if error or enc is None or img is None:
                return jsonify({"success": False, "message": error}), 400
            encodings.append(enc)
            _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            import base64
            thumbnails.append(f"data:image/jpeg;base64,{base64.b64encode(buf.tobytes()).decode('ascii')}")

        now = datetime.utcnow().isoformat()
        display_name = student.get("name", usn)
        serialized = [enc.tolist() for enc in encodings]
        legacy_first = json.dumps(serialized[0])

        db.collection(STUDENTS).document(doc_id).update({
            "face_encoding": legacy_first,
            "face_encodings": serialized,
            "face_registered": True,
            "face_photo": thumbnails[0] if thumbnails else None,
            "face_registered_at": now,
        })
        db.collection(FACE_ENCODINGS).document(usn).set({
            "usn": usn,
            "student_id": doc_id,
            "name": display_name,
            "face_encoding": legacy_first,
            "face_encodings": serialized,
            "face_photos": thumbnails,
            "face_photo": thumbnails[0] if thumbnails else None,
            "registered_at": now,
        })

        return jsonify({
            "success": True,
            "message": f"Five-angle face registered for {display_name}",
            "usn": usn,
            "faceRegistered": True,
            "encodings": len(serialized),
        })

    if not image_data:
        return jsonify({"success": False, "message": "USN and either images or image_data are required"}), 400

    ok, msg = store_face_encoding_for_usn(usn, image_data)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    return jsonify({
        "success": True,
        "message": msg,
        "usn": usn,
        "faceRegistered": True,
    })


# ── Recognize faces in frame (real-time attendance) ───────────────────────────
@face_bp.route("/recognize", methods=["POST"])
def recognize_face():
    if not FACE_RECOGNITION_AVAILABLE:
        return jsonify({"success": False, "message": "face_recognition library not installed"}), 500

    data = request.json or {}
    image_data = data.get("image_data")
    subject_code = data.get("subject_code", "")

    if not image_data:
        return jsonify({"success": False, "message": "image_data is required"}), 400

    try:
        img = _decode_image(image_data)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model="hog")
    frame_encodings = face_recognition.face_encodings(rgb, boxes)

    if not frame_encodings:
        return jsonify({
            "success": True,
            "recognized": False,
            "faces_in_frame": 0,
            "matches": [],
            "message": "No face detected in frame",
            "subject_code": subject_code,
        })

    registered = _load_registered_encodings()
    if not registered:
        return jsonify({
            "success": True,
            "recognized": False,
            "faces_in_frame": len(frame_encodings),
            "matches": [],
            "message": "No registered faces in database. Students must register first.",
            "subject_code": subject_code,
        })

    seen_usns: set[str] = set()
    matches = []

    for enc in frame_encodings:
        best_match = None
        for usn, name, known_encodings in registered:
            if usn in seen_usns or not known_encodings:
                continue
            matched_flags = face_recognition.compare_faces(known_encodings, enc, tolerance=MATCH_TOLERANCE)
            confidence = round((sum(1 for flag in matched_flags if flag) / len(known_encodings)) * 100)
            if confidence >= 60 and (best_match is None or confidence > best_match["confidence"]):
                best_match = {"usn": usn, "name": name, "confidence": confidence}

        if best_match:
            seen_usns.add(best_match["usn"])
            matches.append(best_match)

    message = None
    if not matches:
        message = UNRECOGNIZED_MSG

    return jsonify({
        "success": True,
        "recognized": len(matches) > 0,
        "matched": len(matches) > 0,
        "usn": matches[0]["usn"] if matches else None,
        "student_name": matches[0]["name"] if matches else None,
        "confidence": matches[0]["confidence"] if matches else 0,
        "faces_in_frame": len(frame_encodings),
        "matches": matches,
        "subject_code": subject_code,
        "message": message,
    })


# ── Face status ───────────────────────────────────────────────────────────────
@face_bp.route("/status", methods=["GET"])
def face_status_query():
    usn = (request.args.get("usn") or "").strip().upper()
    if not usn:
        return jsonify({"error": "USN is required"}), 400
    return _face_status_response(usn)


@face_bp.route("/status/<usn>", methods=["GET"])
def face_status(usn):
    return _face_status_response((usn or "").strip().upper())


def _face_status_response(usn: str):
    enc_doc = db.collection(FACE_ENCODINGS).document(usn).get()
    enc_data = enc_doc.to_dict() or {}

    if enc_doc.exists:
        return jsonify({
            "registered": True,
            "registered_at": _serialize_timestamp(enc_data.get("registered_at")),
            "faceRegistered": True,
            "face_registered": True,
            "hasPhoto": bool(enc_data.get("face_photo")),
            "usn": usn,
        })

    return jsonify({
        "registered": False,
        "faceRegistered": False,
        "face_registered": False,
        "hasPhoto": False,
        "usn": usn,
    })
