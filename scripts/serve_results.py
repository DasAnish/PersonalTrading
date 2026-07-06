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

if __name__ == "__main__":
    HOST = "127.0.0.1"
    PORT = 5000

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
