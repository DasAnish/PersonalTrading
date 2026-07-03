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

from server.app import create_app

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Strategy Backtest Dashboard")
    print("=" * 60)
    print("\n[*] Starting server...\n")
    print("[*] Open your browser and navigate to: http://localhost:5000\n")
    print("Press Ctrl+C to stop the server\n")
    print("=" * 60 + "\n")

    app = create_app()
    app.run(debug=True, port=5000)
