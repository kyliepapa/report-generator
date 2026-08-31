"""
Analytics API routes (read + patch). Writes also happen from report/pdf job routes.
"""

from flask import Blueprint, request, jsonify

import core.analytics as analytics

analytics_bp = Blueprint("analytics_routes", __name__)


@analytics_bp.route("/analytics/runs")
def get_runs():
    user_id = request.args.get("user_id") or None
    run_type = request.args.get("run_type") or None
    limit = request.args.get("limit")
    limit_n = int(limit) if limit and limit.isdigit() else None
    runs = analytics.list_runs(user_id=user_id, run_type=run_type, limit=limit_n)
    return jsonify({"runs": runs})


@analytics_bp.route("/analytics/overview")
def get_overview():
    user_id = request.args.get("user_id") or None
    return jsonify(analytics.compute_overview(user_id=user_id))


@analytics_bp.route("/analytics/users")
def get_users():
    return jsonify({"users": analytics.list_user_ids()})


@analytics_bp.route("/analytics/patch_report_edits", methods=["POST"])
def patch_report_edits():
    data = request.json or {}
    run_id = data.get("run_id")
    edits = data.get("edits")
    if not run_id or not isinstance(edits, dict):
        return jsonify({"error": "run_id and edits required"}), 400
    ok = analytics.patch_report_edits(run_id, edits)
    if not ok:
        return jsonify({"error": "run not found"}), 404
    return jsonify({"ok": True})


@analytics_bp.route("/analytics/run/<run_id>")
def get_run(run_id):
    record = analytics.load_run(run_id)
    if not record:
        return jsonify({"error": "not found"}), 404
    return jsonify(record)
