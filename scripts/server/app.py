"""Flask app factory for the dashboard server."""

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)

    from .api import bp as api_bp
    from .routes import bp as routes_bp

    app.register_blueprint(routes_bp)
    app.register_blueprint(api_bp)

    return app
