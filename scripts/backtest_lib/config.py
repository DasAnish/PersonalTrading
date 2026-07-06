"""Shared configuration for the backtest CLI."""

import json
from datetime import datetime, timedelta
from pathlib import Path

# Assets are read dynamically from strategy_definitions/assets/
_ASSETS_DIR = Path(__file__).parent.parent.parent / "strategy_definitions" / "assets"
SYMBOLS = sorted(
    json.loads(p.read_text())["parameters"]["symbol"]
    for p in _ASSETS_DIR.glob("*.json")
)

EXCHANGE = "SMART"
CURRENCY = "GBP"
SEC_TYPE = "STK"
INITIAL_CAPITAL = 10000.0  # GBP
TRANSACTION_COST_BPS = 7.5
REBALANCE_FREQUENCY = "monthly"
LOOKBACK_DAYS = 252  # 1 year for HRP calculation
BAR_SIZE = "1 day"

# Date range - fetch maximum available history.
# Use yesterday to account for cache files that might not have today's data yet.
END_DATE = datetime.now() - timedelta(days=1)
START_DATE = END_DATE - timedelta(days=365 * 10)  # Try to get 10 years

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)
