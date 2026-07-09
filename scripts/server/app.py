"""Flask app factory for the dashboard server."""

from flask import Flask


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)

    from .api import bp as api_bp
    from .routes import bp as routes_bp
    from .risk import risk_bp
    from .jobs import jobs_bp

    app.register_blueprint(routes_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(risk_bp)
    app.register_blueprint(jobs_bp)

    return app
