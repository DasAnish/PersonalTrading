"""Page routes for the dashboard server."""

from flask import Blueprint, render_template

bp = Blueprint(
    "routes",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


@bp.route("/")
def overview():
    """Serve the strategies overview page."""
    return render_template("overview.html")


@bp.route("/strategy/")
@bp.route("/strategy/<strategy_key>")
def strategy_detail(strategy_key: str = None):
    """Serve the strategy detail page."""
    return render_template(
        "strategy.html",
        strategy_key=strategy_key or "Strategy",
    )
