from flask import request, session, redirect, url_for, jsonify

from app_state import app
from web_endpoints_control import control_bp
from web_endpoints_ui import ui_bp

def create_app():
    """Creates and configures the Flask application."""
    app.register_blueprint(control_bp)
    app.register_blueprint(ui_bp)

    @app.before_request
    def before_request_func():
        # Skip auth check for static files, login, favicon, and logout
        is_public_endpoint = request.endpoint in ['static', 'ui.login', 'ui.favicon', 'ui.logout']
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

        if is_public_endpoint:
            return
        if not session.get('logged_in'):
            if is_ajax:
                return jsonify(error='Unauthorized'), 401
            return redirect(url_for('ui.login'))

    return app