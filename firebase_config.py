"""
firebase_config.py
──────────────────
Initialises the Firebase Admin SDK once and exposes:
  • db  – Firestore client  (google.cloud.firestore.Client)

All route modules import from here.
"""

import os
import firebase_admin
from firebase_admin import credentials, firestore

_SERVICE_ACCOUNT_PATH = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")

def _init_firebase() -> firestore.client:
    if not firebase_admin._apps:
        cred = credentials.Certificate(_SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred)
    return firestore.client()


# Singleton Firestore client – imported by every route file
db: firestore.Client = _init_firebase()

# ── Collection helpers ──────────────────────────────────────────────────────────
USERS                   = "users"
STUDENTS                = "students"
TEACHERS                = "teachers"
ATTENDANCE              = "attendance"
MARKS                   = "cie_marks"
NOTIFICATIONS           = "notifications"
SUBJECTS                = "subjects"
SECTIONS                = "sections"
TIMETABLE               = "timetable"
FACE_ENCODINGS          = "face_encodings"
ACTIVITY_LOGS           = "activity_logs"
CONDONATION_REQUESTS    = "condonation_requests"

# All collections wiped by wipe_and_reset.py
ALL_COLLECTIONS = [
    USERS,
    STUDENTS,
    TEACHERS,
    SECTIONS,
    SUBJECTS,
    MARKS,
    ATTENDANCE,
    NOTIFICATIONS,
    TIMETABLE,
    FACE_ENCODINGS,
    ACTIVITY_LOGS,
    CONDONATION_REQUESTS,
]
