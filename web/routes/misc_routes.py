"""
Misc routes: changelog display, R&R submission form, and the dev
file-editor endpoints. Relocated from app.py with no logic changes --
file path constants and the read/write/append helpers now come from
core.paths instead of being defined locally.
"""

from datetime import datetime

from flask import Blueprint, request, jsonify

import core.paths as paths

misc_bp = Blueprint("misc_routes", __name__)


@misc_bp.route('/get_changelog')
def get_changelog():
    return jsonify({'content': paths.read_file(paths.CHANGELOG_FILE)})


@misc_bp.route('/submit_rnr', methods=['POST'])
def submit_rnr():
    data      = request.json
    message   = data.get('message', '').strip()
    submitter = data.get('submitter', '').strip()
    if not message or not submitter:
        return jsonify({'error': 'Missing fields'}), 400

    ts    = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    entry = f"{ts}\n{message}\nSubmitted by: {submitter}\n\n"
    paths.append_file(paths.REPNREQ_FILE, entry)
    return jsonify({'ok': True})


@misc_bp.route('/dev_get_file')
def dev_get_file():
    file_key = request.args.get('file')
    file_paths = {
        'usage_logs': paths.USAGE_LOGS_FILE,
        'repnreq':    paths.REPNREQ_FILE,
    }
    path = file_paths.get(file_key)
    if not path:
        return jsonify({'error': 'Unknown file'}), 400
    return jsonify({'content': paths.read_file(path)})


@misc_bp.route('/dev_save_file', methods=['POST'])
def dev_save_file():
    data     = request.json
    file_key = data.get('file')
    content  = data.get('content', '')
    file_paths = {
        'usage_logs': paths.USAGE_LOGS_FILE,
        'repnreq':    paths.REPNREQ_FILE,
    }
    path = file_paths.get(file_key)
    if not path:
        return jsonify({'error': 'Unknown file'}), 400
    paths.write_file(path, content)
    return jsonify({'ok': True})