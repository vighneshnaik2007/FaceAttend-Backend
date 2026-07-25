<div align="center">

<img src="./screenshots/face-recognition.png" alt="FaceAttend Face Recognition" width="100%"/>

# ⚙️ FaceAttend — Backend

### Python Flask API with Real-Time Face Recognition

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.3+-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com/)
[![Firebase](https://img.shields.io/badge/Firebase-Firestore-FFCA28?style=for-the-badge&logo=firebase)](https://firebase.google.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=for-the-badge&logo=opencv)](https://opencv.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker)](Dockerfile)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

**Frontend Repo →** [FaceAttend---frontend](https://github.com/vighneshnaik2007/FaceAttend---frontend)

</div>

---

## 📌 Overview

This is the **Python Flask backend** for FaceAttend — an AI-based attendance management system built for college classrooms. It powers all business logic, database operations, and the core face recognition pipeline.

The backend exposes **72 REST API endpoints** across 14 route blueprints, uses **Firebase Firestore** as the primary database, and implements a **5-stage face recognition pipeline** using `dlib` and `face_recognition` for real-time student identification.

Built as an **IPBL (Interdisciplinary Project Based Learning) semester project** at M S Ramaiah Institute of Technology, Bengaluru.

---

## 📸 Face Recognition in Action

<div align="center">
  <img src="./screenshots/face-recognition.png" alt="Live Face Recognition — 3 students detected simultaneously" width="80%"/>
  <br/>
  <sub><i>Live recognition: Vaibhav Milind Jadhav (83% match) · Yallaling Metre (100% match) · Vighnesh V Naik (100% match) — auto-marked present</i></sub>
</div>

---

## 🧠 AI/ML Pipeline

The face recognition system runs a **5-stage pipeline** on every webcam frame:

```
Stage 1 → Face Detection      (dlib HOG-based detector)
Stage 2 → Image Preprocessing (OpenCV decode + normalize)
Stage 3 → Feature Extraction  (128-dimensional ResNet face encoding)
Stage 4 → Face Matching       (compare_faces with tolerance=0.5)
Stage 5 → Confidence Scoring  (1 − face_distance → percentage match)
```

**Registration:** Students register 5 face angles (straight, left, right, up, down). Each image produces a 128-dim encoding vector stored in Firestore for fast lookup during recognition.

**Recognition:** Each webcam frame is decoded via OpenCV → face detected → encoded → compared against all registered student encodings. Match confidence is displayed as a percentage. Students above threshold are auto-marked present.

---

## ✨ Features

- **Real-time face recognition** — identify multiple students in a single frame simultaneously
- **5-angle face registration** — higher accuracy than single-image registration
- **Manual & bulk attendance marking** with date-lock to today
- **Past attendance editing** — modify any historical record
- **Defaulter detection** — students below 75% attendance flagged automatically
- **Shortage alert emails** — Gmail SMTP sends automatic alerts when student drops below 75%
- **CIE & SEE marks** management with grade computation (O/A+/A/B+/B/C/P/F scale)
- **CGPA calculation** from grade points across all subjects
- **Attendance & marks prediction** analytics
- **Condonation request** handling with Cloudinary document upload
- **PDF & Excel exports** via ReportLab and OpenPyXL
- **Admin audit trail** — chronological log of all CRUD actions
- **Email OTP** for forgot password flow
- **Weekly timetable** management per section
- **Docker-ready** for deployment

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| Framework | Flask 2.3+ |
| WSGI Server | Gunicorn 21+ |
| Database | Firebase Firestore (primary) |
| Face Detection | dlib (HOG-based) |
| Face Encoding | face_recognition 1.3+ (128-dim ResNet) |
| Image Processing | OpenCV (headless) |
| Numerical Computing | NumPy |
| Email | Gmail SMTP via smtplib + Flask-Mail |
| File Storage | Cloudinary (condonation documents) |
| PDF Export | ReportLab |
| Excel Export | OpenPyXL |
| Containerization | Docker |

---

## 📁 Project Structure

```
FaceAttend-Backend/
├── app.py                      # Entry point: Flask app, CORS, blueprint registration
├── firebase_config.py          # Firebase Admin SDK singleton + collection constants
├── wipe_and_reset.py           # Firestore reset + seed admin account utility
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker configuration
├── Procfile                    # Gunicorn process file
├── railway.json                # Railway deployment config
├── .env                        # Environment variables (never commit this)
│
├── routes/                     # 14 Flask blueprints
│   ├── auth.py                 # Login, logout, OTP
│   ├── admin.py                # Teacher/student/section CRUD, stats
│   ├── students.py             # Student CRUD
│   ├── attendance.py           # Mark, bulk-mark, history, defaulters, edit
│   ├── marks.py                # CIE/SEE marks, grade computation, CGPA
│   ├── face.py                 # Face registration + recognition
│   ├── notifications.py        # In-app notifications, shortage alerts
│   ├── analytics.py            # Attendance prediction, dashboards
│   ├── timetable.py            # Section/teacher timetable CRUD, holidays
│   ├── reports.py              # Daily/monthly reports
│   ├── export.py               # PDF + Excel exports
│   ├── condonation.py          # Condonation requests + Cloudinary upload
│   ├── activity_log.py         # Admin audit trail
│   └── forgot_password.py      # OTP generation, email, verification
│
└── services/
    ├── notifications.py        # Gmail SMTP shortage alert engine
    └── student_face_register.py # Face encoding extraction + Firestore persistence
```

---

## 🗃️ Database Schema (Firestore Collections)

| Collection | Description |
|------------|-------------|
| `users` | Admin accounts |
| `teachers` | Faculty with subject assignments |
| `students` | Students with face encodings |
| `attendance` | Records keyed as `{usn}_{subject_code}_{date}` |
| `cie_marks` | CIE/SEE marks keyed as `{usn}_{subject_code}` |
| `subjects` | Subject catalog |
| `sections` | Section definitions per semester |
| `timetable` | Schedule entries per section |
| `face_encodings` | 128-dim face encoding vectors by USN |
| `notifications` | In-app + email log |
| `activity_logs` | Admin audit trail |
| `condonation_requests` | Student condonation submissions |
| `password_resets` | OTP storage with 10-min expiry |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Firebase project with Firestore enabled
- Gmail account with App Password enabled
- Cloudinary account (free tier)
- C++ build tools (required for dlib compilation)

### Installation

```bash
# Clone the repository
git clone https://github.com/vighneshnaik2007/FaceAttend-Backend.git
cd FaceAttend-Backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

> ⚠️ **Note on dlib:** `dlib` requires CMake and C++ build tools. On Windows, install [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) first. On Ubuntu: `sudo apt-get install build-essential cmake`.

### Environment Variables

Create a `.env` file in the root directory:

| Variable | Description |
|----------|-------------|
| `GMAIL_USER` | Gmail address for sending alerts and OTPs |
| `GMAIL_PASSWORD` | Gmail App Password (not your regular password) |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `GOOGLE_CREDENTIALS` | Full contents of Firebase `serviceAccountKey.json` as a JSON string |
| `FLASK_ENV` | `development` or `production` |

```env
GMAIL_USER=your_email@gmail.com
GMAIL_PASSWORD=your_app_password
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
GOOGLE_CREDENTIALS={"type":"service_account","project_id":"..."}
FLASK_ENV=development
```

### Firebase Setup

1. Go to [Firebase Console](https://console.firebase.google.com/) → your project → Project Settings → Service Accounts
2. Click **Generate New Private Key** → download `serviceAccountKey.json`
3. Copy the entire JSON content and paste it as the value of `GOOGLE_CREDENTIALS` in your `.env` file
4. The file itself (`serviceAccountKey.json`) can also be placed in the project root as a fallback

### Running the Server

```bash
python app.py
```

Server starts at `http://127.0.0.1:5000`

For production:
```bash
gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 120 app:app
```

---

## 📡 API Reference

### Base URL
```
http://localhost:5000
```

### Health Check
```
GET  /              → Status + college + db info
GET  /api/health    → {"status": "ok"}
```

### Auth — `/api/auth`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/login` | Login by role (admin/teacher/student) |
| POST | `/logout` | Clear session |
| POST | `/forgot-password` | Send OTP to email |
| POST | `/verify-otp` | Verify OTP + update password |

### Face — `/api/face`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register face (single or 5-angle) |
| POST | `/recognize` | Recognize faces in webcam frame |
| GET | `/status?usn=USN` | Check registration status |
| GET | `/health` | Library availability + registered count |

### Attendance — `/api/attendance`
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/mark` | Single attendance record |
| POST | `/mark-bulk` | Batch mark multiple students |
| GET | `/today/<subject_code>` | Today's roster with % |
| GET | `/student/<usn>` | Per-subject attendance summary |
| GET | `/defaulters/<subject_code>` | Students below 75% |
| GET | `/weekly/<subject_code>` | Mon–Sat weekly summary |
| POST | `/edit` | Edit historical attendance |

### Marks — `/api/marks`
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/<subject_code>` | All students' CIE/SEE marks |
| GET | `/student/<usn>` | All subjects' marks + CGPA |
| POST | `/save` | Batch save/update marks |
| GET | `/stats/<subject_code>` | Avg, highest, lowest, pass/fail |

### Export — `/api/export`
| Method | Endpoint | Format |
|--------|----------|--------|
| GET | `/attendance/pdf/<subject_code>` | PDF (ReportLab) |
| GET | `/attendance/excel/<subject_code>` | XLSX (OpenPyXL) |
| GET | `/marks/pdf/<subject_code>` | PDF (ReportLab) |
| GET | `/marks/excel/<subject_code>` | XLSX (OpenPyXL) |

> Full API documentation with all 72 endpoints is available across the 14 route files in `/routes/`.

---

## 🐳 Docker

```bash
# Build the image
docker build -t faceattend-backend .

# Run the container
docker run -p 5000:5000 --env-file .env faceattend-backend
```

---

## 👨‍💻 Team

Built by a 5-member team as part of the **IPBL Semester Project** at **M S Ramaiah Institute of Technology, Bengaluru (VTU-affiliated)**.

| Name | GitHub |
|------|--------|
| Vighnesh V Naik | [@vighneshnaik2007](https://github.com/vighneshnaik2007) |
| Vaibhav Milind Jadhav | [@vaibhavjadhav0210](https://github.com/vaibhavjadhav0210) |
| Yallaling Metre | — |
| Vinaykumar | — |
| Yathin Gowda P | — |

---

## 🔗 Related

- 🎨 **Frontend Repository:** [FaceAttend---frontend](https://github.com/vighneshnaik2007/FaceAttend---frontend)
- 👤 **GitHub:** [vighneshnaik2007](https://github.com/vighneshnaik2007)

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">
  <sub>Built with ❤️ at MSRIT, Bengaluru | IPBL 2026</sub>
</div>
