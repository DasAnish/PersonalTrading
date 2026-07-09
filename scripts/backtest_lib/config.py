"""Shared configuration for the backtest CLI."""

import json
from datetime import datetime, timedelta
from pathlib import Path

# Assets are read dynamically from strategy_definitions/assets/
_ASSETS_DIR = Path(__file__).parent.parent.parent / "strategy_definitions" / "assets"

EXCHANGE = "SMART"
CURRENCY = "GBP"
SEC_TYPE = "STK"

# Per-symbol IB contract parameters. Assets may quote in a non-GBP currency
# (e.g. EMMCHA=CHF, EXSA=EUR, HYLD=USD) — requesting them as GBP returns no
# contract at all, so each fetch must use the asset's own declared params,
# falling back to the globals above when a field is absent.
SYMBOL_SPECS = {}
for _p in _ASSETS_DIR.glob("*.json"):
    _params = json.loads(_p.read_text())["parameters"]
    SYMBOL_SPECS[_params["symbol"]] = {
        "currency": _params.get("currency", CURRENCY),
        "exchange": _params.get("exchange", EXCHANGE),
        "sec_type": _params.get("sec_type", SEC_TYPE),
    }

SYMBOLS = sorted(SYMBOL_SPECS)
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
