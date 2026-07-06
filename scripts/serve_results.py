#!/usr/bin/env python3
"""
Interactive web dashboard for portfolio strategy backtest results.

Run with: python scripts/serve_results.py
Then visit: http://localhost:5000
"""

import sys
from pathlib import Path

# Ensure scripts/ is on the path so the server package can be imported, and
# the repo root is on the path so scripts/server/data.py can import the
# top-level backtesting/results_schema module.
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from waitress import serve

from server.app import create_app


def _check_port_free(host: str, port: int) -> None:
    """Exit with a clear message if something is already bound to host:port.

    On Windows a second server can silently co-bind and the *old* process keeps
    answering, so a stale server would otherwise mask a restart entirely.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex((host, port)) == 0:
            raise SystemExit(
                f"ERROR: {host}:{port} is already in use — a dashboard server is "
                f"probably still running. Stop it first (PowerShell: "
                f"Get-NetTCPConnection -LocalPort {port} -State Listen | "
                f"Select OwningProcess), then restart."
            )


if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 5000

    _check_port_free(HOST, PORT)

    print("\n" + "=" * 60)
    print("Strategy Backtest Dashboard")
    print("=" * 60)
    print("\n[*] Starting server (waitress, production WSGI)...\n")
    print(f"[*] Open your browser and navigate to: http://localhost:{PORT}\n")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60 + "\n")

    app = create_app()
    # waitress is a stable, threaded WSGI server: no debug auto-reloader, so the
    # process keeps running for as long as you leave it up (it will NOT restart
    # or die when source files change). Restart it manually to pick up code edits.
    serve(app, host=HOST, port=PORT)
