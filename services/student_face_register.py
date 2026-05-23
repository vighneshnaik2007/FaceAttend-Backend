"""
Shared face encoding + Firestore persistence for students (USN doc id).
Used by POST /api/face/register and POST /api/admin/add-student (optional image_data).
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

import cv2
import numpy as np

from firebase_config import FACE_ENCODINGS, STUDENTS, db

logger = logging.getLogger(__name__)

try:
    import face_recognition

    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    face_recognition = None  # type: ignore
    FACE_RECOGNITION_AVAILABLE = False


def decode_image_data_url(image_data: str):
    if "," in image_data:
        _, encoded = image_data.split(",", 1)
    else:
        encoded = image_data
    img_bytes = base64.b64decode(encoded)
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image")
    return img


def _thumbnail_data_url(img_bgr, max_width: int = 320) -> str:
    h, w = img_bgr.shape[:2]
    if w > max_width:
        scale = max_width / w
        img_bgr = cv2.resize(img_bgr, (max_width, int(h * scale)))
    _, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _get_student_doc(usn: str):
    usn = (usn or "").upper()
    doc = db.collection(STUDENTS).document(usn).get()
    if doc.exists:
        return doc.id, doc.to_dict()
    docs = list(db.collection(STUDENTS).where("usn", "==", usn).limit(1).stream())
    if not docs:
        return None, None
    return docs[0].id, docs[0].to_dict()


def store_face_encoding_for_usn(usn: str, image_data: str) -> tuple[bool, str]:
    """
    Compute encoding from base64 image, save to students + face_encodings/{USN}.
    Returns (success, message).
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return False, "face_recognition library not installed on server"

    usn = (usn or "").upper()
    if not image_data:
        return False, "image_data is required"

    try:
        img = decode_image_data_url(image_data)
    except ValueError as exc:
        return False, str(exc)

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model="hog")
    encodings = face_recognition.face_encodings(rgb, boxes)

    if not encodings:
        return False, "No face detected. Use good lighting and a clear front-facing photo."

    if len(encodings) > 1:
        return False, "Multiple faces detected. Only the student should be in the photo."

    doc_id, student = _get_student_doc(usn)
    if not student:
        return False, "Student USN not found"

    encoding_str = json.dumps(encodings[0].tolist())
    photo_url = _thumbnail_data_url(img)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    display_name = student.get("name", usn)

    db.collection(STUDENTS).document(doc_id).update({
        "face_encoding": encoding_str,
        "face_registered": True,
        "face_photo": photo_url,
        "face_registered_at": now,
    })
    db.collection(FACE_ENCODINGS).document(usn).set({
        "usn": usn,
        "student_id": doc_id,
        "name": display_name,
        "face_encoding": encoding_str,
        "face_photo": photo_url,
        "registered_at": now,
    })
    return True, f"Face registered for {display_name}"
