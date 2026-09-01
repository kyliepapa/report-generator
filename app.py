"""
Flask entry point.

Was ~486 lines mixing app setup, path config, file I/O helpers, the
job store, apply_photo_edits, and every route handler in one file.
All of that moved out:
  - path config + file I/O helpers -> core/paths.py
  - job store                       -> core/job_manager.py
  - apply_photo_edits               -> core/photo_edits.py
  - route handlers                  -> web/routes/*.py

This file's only job now is creating the Flask app and registering
routes.
"""
import os
from flask import Flask, send_from_directory

import core.timezone  # noqa: F401 -- configure Pacific TZ before other imports use datetime
import core.paths as paths  # noqa: F401 -- imported for its side effect of
                             # creating STATIC_DIR/REPORTS_DIR on startup
from web.routes import register_routes

app = Flask(__name__, template_folder="web/landing/templates")

@app.route("/scripts/<path:filename>")
def serve_landing_scripts(filename):
    scripts_dir = os.path.join(app.root_path, "web", "landing", "scripts")
    return send_from_directory(scripts_dir, filename)

register_routes(app)


if __name__ == '__main__':
    app.run(debug=True)

