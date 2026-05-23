"""
routes/activity_log.py  —  Admin activity logging endpoints
"""

from flask import Blueprint, jsonify, request
from firebase_config import ACTIVITY_LOGS, db

activity_log_bp = Blueprint("activity_log", __name__)


@activity_log_bp.route("/activity-log", methods=["GET"])
def get_activity_logs():
    """
    GET /api/admin/activity-log?limit=50
    Returns recent admin activity logs ordered by timestamp descending
    """
    limit = request.args.get("limit", default=50, type=int)
    if limit > 200:
        limit = 200  # Cap at 200 for performance
    if limit < 1:
        limit = 1

    logs = []
    try:
        query = db.collection(ACTIVITY_LOGS).order_by("timestamp", direction="DESCENDING").limit(limit)
        for doc in query.stream():
            log_data = doc.to_dict()
            logs.append({
                "id": doc.id,
                "action_type": log_data.get("action_type"),
                "performed_by": log_data.get("performed_by"),
                "target_name": log_data.get("target_name"),
                "target_id": log_data.get("target_id"),
                "timestamp": log_data.get("timestamp"),
                "details": log_data.get("details"),
            })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

    return jsonify({"success": True, "logs": logs})


def log_admin_activity(action_type: str, target_name: str, target_id: str, details: str):
    """
    Helper function to log admin actions to Firestore
    action_type: one of teacher_added / teacher_deleted / teacher_edited / student_added / student_deleted / student_edited
    """
    from datetime import datetime

    try:
        log_entry = {
            "action_type": action_type,
            "performed_by": "System Administrator",
            "target_name": target_name,
            "target_id": target_id,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
        }
        db.collection(ACTIVITY_LOGS).add(log_entry)
    except Exception as e:
        print(f"Error logging admin activity: {e}")
