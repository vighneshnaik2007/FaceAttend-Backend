import subprocess
import sys

# Install face_recognition_models if missing
try:
    import face_recognition_models
except ImportError:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "git+https://github.com/ageitgey/face_recognition_models"
    ])

"""
app.py
──────
Entry-point for the FaceAttend Flask backend.
Database: Firebase Firestore  (via firebase-admin)
"""

import os

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from flask_mail import Mail

load_dotenv()

from routes.auth          import auth_bp
from routes.admin         import admin_bp
from routes.students      import students_bp
from routes.attendance    import attendance_bp
from routes.forgot_password import forgot_password_bp
from routes.marks         import marks_bp
from routes.notifications import notifications_bp
from routes.face          import face_bp
from routes.reports       import reports_bp
from routes.analytics     import analytics_bp
from routes.timetable     import timetable_bp
from routes.export        import export_bp
from routes.activity_log  import activity_log_bp
from routes.condonation   import condonation_bp

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "faceattend_rit_secret_2026")

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("GMAIL_USER", "")
app.config["MAIL_PASSWORD"] = os.environ.get("GMAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("GMAIL_USER", "")

mail = Mail(app)

CORS(
    app,
    resources={r"/*": {"origins": "*"}},
    supports_credentials=True,
)

app.register_blueprint(auth_bp,          url_prefix="/api/auth")
app.register_blueprint(forgot_password_bp, url_prefix="/api/auth")
app.register_blueprint(admin_bp,         url_prefix="/api/admin")
app.register_blueprint(activity_log_bp,  url_prefix="/api/admin")
app.register_blueprint(condonation_bp,   url_prefix="/api/condonation")
app.register_blueprint(students_bp,      url_prefix="/api/students")
app.register_blueprint(attendance_bp,    url_prefix="/api/attendance")
app.register_blueprint(marks_bp,         url_prefix="/api/marks")
app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
app.register_blueprint(face_bp,          url_prefix="/api/face")
app.register_blueprint(reports_bp,       url_prefix="/api/reports")
app.register_blueprint(analytics_bp,     url_prefix="/api/analytics")
app.register_blueprint(timetable_bp,     url_prefix="/api/timetable")
app.register_blueprint(export_bp,        url_prefix="/api/export")


@app.route("/")
def health():
    return {
        "status":  "FaceAttend API running",
        "college": "FaceAttend",
        "db":      "Firebase Firestore",
    }


@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_ENV") == "development", port=5000)