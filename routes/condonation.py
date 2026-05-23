"""
routes/condonation.py  —  Condonation request endpoints for students and teachers
"""

import os
from datetime import datetime

import cloudinary
import cloudinary.uploader
from werkzeug.utils import secure_filename
from flask import Blueprint, jsonify, request
from firebase_config import CONDONATION_REQUESTS, db

condonation_bp = Blueprint("condonation", __name__)

ALLOWED_DOCUMENT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
MAX_DOCUMENT_SIZE = 5 * 1024 * 1024

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)


def _request_payload(req_data):
    return {
        "id": req_data["id"],
        "usn": req_data.get("usn"),
        "subject_code": req_data.get("subject_code"),
        "reason": req_data.get("reason"),
        "supporting_details": req_data.get("supporting_details"),
        "status": req_data.get("status"),
        "timestamp": req_data.get("timestamp"),
        "teacher_remarks": req_data.get("teacher_remarks", ""),
        "document_urls": req_data.get("document_urls", []),
    }


@condonation_bp.route("/upload-document", methods=["POST"])
def upload_condonation_document():
    file = request.files.get("file")
    usn = (request.form.get("usn") or "").strip().upper()
    subject_code = (request.form.get("subject_code") or "").strip().upper()

    if not file or not usn or not subject_code:
        return jsonify({"success": False, "message": "file, usn, and subject_code are required"}), 400

    filename = secure_filename(file.filename or "")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        return jsonify({"success": False, "message": "Only PDF, JPG, JPEG, and PNG files are allowed"}), 400

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > MAX_DOCUMENT_SIZE:
        return jsonify({"success": False, "message": f"File {filename} exceeds 5MB limit"}), 400

    content_type = file.mimetype or {
        "pdf": "application/pdf",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
    }.get(extension, "application/octet-stream")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    public_id = f"{usn}/{subject_code}/{timestamp}-{filename.rsplit('.', 1)[0]}"

    try:
        upload_response = cloudinary.uploader.upload(
            file,
            folder="condonation-docs",
            public_id=public_id,
            resource_type="auto",
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

    secure_url = upload_response.get("secure_url")
    if not secure_url:
        return jsonify({"success": False, "message": "Cloudinary upload did not return a secure URL"}), 500

    return jsonify({
        "success": True,
        "url": secure_url,
        "filename": filename,
        "content_type": content_type,
    })


@condonation_bp.route("/request", methods=["POST"])
def create_condonation_request():
    """
    POST /api/condonation/request
    Body: {usn, subject_code, reason, supporting_details}
    Creates a new condonation request with status: "pending"
    """
    data = request.json or {}
    usn = (data.get("usn") or "").strip().upper()
    subject_code = (data.get("subject_code") or "").strip().upper()
    reason = (data.get("reason") or "").strip()
    supporting_details = (data.get("supporting_details") or "").strip()
    document_urls = data.get("document_urls") or []

    if not usn or not subject_code or not reason:
        return jsonify({"success": False, "message": "usn, subject_code, and reason are required"}), 400
    if not isinstance(document_urls, list) or any(not isinstance(url, str) for url in document_urls):
        return jsonify({"success": False, "message": "document_urls must be an array of strings"}), 400

    try:
        condonation_request = {
            "usn": usn,
            "subject_code": subject_code,
            "reason": reason,
            "supporting_details": supporting_details,
            "status": "pending",
            "timestamp": datetime.utcnow().isoformat(),
            "teacher_remarks": "",
            "document_urls": document_urls,
        }
        doc_ref = db.collection(CONDONATION_REQUESTS).add(condonation_request)
        request_id = doc_ref[1].id

        return jsonify({
            "success": True,
            "request_id": request_id,
            "message": "Condonation request submitted successfully"
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@condonation_bp.route("/student/<usn>", methods=["GET"])
def get_student_condonation_requests(usn):
    """
    GET /api/condonation/student/<usn>
    Returns all condonation requests for a specific student
    """
    usn = usn.upper()

    try:
        requests = []
        query = db.collection(CONDONATION_REQUESTS).where("usn", "==", usn)
        for doc in query.stream():
            req_data = doc.to_dict()
            req_data["id"] = doc.id
            requests.append(_request_payload(req_data))

        # Sort by timestamp descending
        requests.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return jsonify({"success": True, "requests": requests})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@condonation_bp.route("/teacher/<subject_code>", methods=["GET"])
def get_subject_condonation_requests(subject_code):
    """
    GET /api/condonation/teacher/<subject_code>
    Returns all condonation requests for a specific subject code
    """
    subject_code = subject_code.upper()

    try:
        requests = []
        query = db.collection(CONDONATION_REQUESTS).where("subject_code", "==", subject_code)
        for doc in query.stream():
            req_data = doc.to_dict()
            req_data["id"] = doc.id
            requests.append(_request_payload(req_data))

        # Sort by timestamp descending
        requests.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return jsonify({"success": True, "requests": requests})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@condonation_bp.route("/respond/<request_id>", methods=["PUT"])
def respond_to_condonation_request(request_id):
    """
    PUT /api/condonation/respond/<request_id>
    Body: {status: "approved"/"rejected", teacher_remarks}
    Updates the condonation request status and adds teacher remarks
    """
    data = request.json or {}
    status = (data.get("status") or "").strip().lower()
    teacher_remarks = (data.get("teacher_remarks") or "").strip()

    if status not in ("approved", "rejected"):
        return jsonify({"success": False, "message": "status must be 'approved' or 'rejected'"}), 400

    try:
        ref = db.collection(CONDONATION_REQUESTS).document(request_id)
        if not ref.get().exists:
            return jsonify({"success": False, "message": "Condonation request not found"}), 404

        ref.update({
            "status": status,
            "teacher_remarks": teacher_remarks,
        })

        return jsonify({"success": True, "message": f"Condonation request {status}"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
