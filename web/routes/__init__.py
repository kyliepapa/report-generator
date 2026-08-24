"""
Registers all route blueprints on the Flask app. app.py just calls
register_routes(app) instead of importing/registering each blueprint
itself.
"""

from web.routes.report_routes import report_bp
from web.routes.pdf_routes import pdf_bp
from web.routes.misc_routes import misc_bp


def register_routes(app):
    app.register_blueprint(report_bp)
    app.register_blueprint(pdf_bp)
    app.register_blueprint(misc_bp)