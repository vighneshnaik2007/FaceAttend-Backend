# FaceAttend Backend — Ramaiah Institute of Technology

A Python **Flask** REST API that powers the FaceAttend college attendance system.  
Database: **Firebase Firestore** via `firebase-admin`.  
Face recognition: `face_recognition` (dlib).

---

## Project Structure

```
FaceAttend-backend/
├── app.py                  # Flask entry-point, CORS, Mail, blueprint registration
├── firebase_config.py      # Firebase Admin SDK init — imports db everywhere
├── serviceAccountKey.json  # ← Place your Firebase service account here (NOT committed)
├── requirements.txt
├── Procfile                # gunicorn for Railway / Render
├── services/
│   └── notifications.py    # Gmail shortage email alerts + Firestore log
└── routes/
    ├── __init__.py
    ├── auth.py             # /api/auth/login  /api/auth/logout
    ├── students.py         # /api/students/  /api/students/<usn>
    ├── attendance.py       # /api/attendance/*
    ├── marks.py            # /api/marks/*
    ├── notifications.py    # /api/notifications/*
    ├── face.py             # /api/face/register  /api/face/recognize
    └── reports.py          # /api/reports/subjects  /api/reports/timetable
```

---

## Quick Start

### 1 — Firebase setup

1. Go to [Firebase Console](https://console.firebase.google.com/) → your project → **Project Settings → Service Accounts**.
2. Click **Generate new private key** → download the JSON file.
3. Rename it to `serviceAccountKey.json` and place it in the project root.
4. Enable **Cloud Firestore** in the Firebase console (Native mode).

### 2 — Install dependencies

```bash
pip install -r requirements.txt
```

> **Windows note:** `face_recognition` requires CMake and dlib.  
> Install CMake first: `pip install cmake` then `pip install dlib face_recognition`

### 3 — Environment variables (email)

Copy or create a `.env` file in the project root.  
`app.py` loads it via `python-dotenv`. Use a **Gmail App Password**, not your normal password.

| Variable | Purpose |
|----------|---------|
| `GMAIL_USER` | Gmail address used to send shortage emails |
| `GMAIL_PASSWORD` | Gmail App Password (16 characters) |
| `FLASK_ENV` | Optional; e.g. `development` |

### 4 — Run the server

```bash
python app.py
# → http://localhost:5000
```

---

## API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login teacher or student. Body: `{email, password, role}` |
| POST | `/api/auth/logout` | Clear session |

### Students
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/students/` | List all students |
| POST | `/api/students/` | Add new student |
| GET | `/api/students/<usn>` | Get student + attendance % |
| PUT | `/api/students/<usn>` | Update student |
| DELETE | `/api/students/<usn>` | Delete student |

### Attendance
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/attendance/mark` | Mark one student present/absent (triggers shortage email if % &lt; 75) |
| POST | `/api/attendance/mark-bulk` | Mark whole class at once (same auto-alerts) |
| GET | `/api/attendance/today/<subject_code>` | Today's roll + cumulative `attendance_pct` per student in that subject |
| GET | `/api/attendance/student/<usn>` | Per-subject summary (`percentage` and `attendance_pct`) |
| GET | `/api/attendance/history/<usn>` | Full 60-record history |
| GET | `/api/attendance/defaulters/<subject_code>` | Students below 75 % |
| GET | `/api/attendance/weekly/<subject_code>` | Weekly chart data |
| GET | `/api/attendance/by-date?subject_code=&date=` | Filter by date |
| POST | `/api/attendance/edit` | Correct a record (may trigger shortage alerts) |

### Marks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/marks/<subject_code>` | All student marks for a subject |
| GET | `/api/marks/student/<usn>` | All subjects marks for a student |
| POST | `/api/marks/save` | Upsert CIE marks |
| GET | `/api/marks/stats/<subject_code>` | Avg/high/low stats |

### Notifications
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/notifications/shortage-alerts-log` | Audit log of sent shortage emails (`?limit=`) |
| POST | `/api/notifications/send-shortage-alert` | Body: `{usn, subject_code, attendance_pct?}` — Gmail if below 75% |
| GET | `/api/notifications/<user_id>` | Get in-app notifications (`?role=student`) |
| POST | `/api/notifications/mark-read/<id>` | Mark one read |
| POST | `/api/notifications/mark-all-read` | Mark all read |
| POST | `/api/notifications/send` | Send in-app notification |
| GET | `/api/notifications/unread-count/<user_id>` | Unread count |

### Face
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/face/health` | Check `face_recognition` + OpenCV availability |
| POST | `/api/face/register` | Register face. Body: `{usn, image_data}` — stores encoding + photo on student doc |
| POST | `/api/face/recognize` | Real-time frame match. Body: `{image_data, subject_code}` → `{matches: [{usn, name, confidence}]}` |
| GET | `/api/face/status/<usn>` | Check registration status |

### Reports
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/reports/subjects` | All subjects list |
| GET | `/api/reports/timetable` | Weekly timetable |
| GET | `/api/reports/daily?subject_code=&date=` | Daily report |
| GET | `/api/reports/monthly?subject_code=&year=&month=` | Monthly chart |

---

## Firestore Collection Schema

| Collection | Document ID | Key Fields |
|------------|-------------|------------|
| `students` | auto-id | `usn`, `name`, `face_encoding`, `face_registered` |
| `teachers` | `T001`–`T008` | `email`, `password`, `subject_code` |
| `subjects` | subject code | `name`, `contact_hours`, `color` |
| `attendance` | `USN_CODE_DATE` | `usn`, `subject_code`, `date`, `status` |
| `cie_marks` | `USN_CODE` | `cie1`, `cie2`, `cie3`, `assignment` |
| `notifications` | auto-id | In-app: `user_id`, `user_role`, `read`. Shortage: `category: shortage_alert`, `type: email`, `status`, `alert_group_id`, `student_usn`, `subject_code`, `timestamp` |
| `timetable` | `Day_code_N` | `day`, `subject_code`, `start_time`, `end_time` |

---

## Deployment

### Railway / Render (recommended)
The `Procfile` is already configured:
```
web: gunicorn app:app
```
Add `serviceAccountKey.json` contents as an environment variable **GOOGLE_APPLICATION_CREDENTIALS_JSON** and update `firebase_config.py` to read from it if needed.

---

## Notes
- `face_recognition` is optional — all other endpoints work without it.
- CORS is pre-configured for `localhost:3000`, `*.railway.app`, `*.vercel.app`.
- Firestore composite indexes may be needed for some compound queries — the Firebase console will show index creation links in error messages.
