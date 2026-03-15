"""
Interactive Brokers MCP Server

Exposes IB market data, portfolio, and backtesting capabilities as MCP tools
so they can be called directly from Claude Code or Claude Desktop.

Behaviour
---------
* Market data tools – try IB Gateway first, fall back to local parquet cache.
* Portfolio tools   – require a live IB connection (port 4001 by default).
* Backtest tools    – run via the existing scripts/run_backtest.py engine;
                      cached market data is used automatically.

Register with Claude Code
-------------------------
    claude mcp add ib-trading -- python mcp_server/server.py

Or add .mcp.json to the project root (already created alongside this file).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd

# ── Project root on sys.path so local packages are importable ─────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── IB client singleton ────────────────────────────────────────────────────────
_ib_client = None
_ib_connected: bool = False


async def _get_ib_client():
    """
    Return a connected IBClient, or None when IB Gateway is not reachable.

    Connection is attempted once and then reused for the lifetime of the
    server process.
    """
    global _ib_client, _ib_connected

    if _ib_connected and _ib_client is not None:
        return _ib_client

    try:
        from ib_wrapper.client import IBClient  # noqa: PLC0415

        _ib_client = IBClient()          # reads host/port from .env automatically
        _ib_connected = await asyncio.wait_for(_ib_client.connect(), timeout=10)

        if _ib_connected:
            logger.info("Connected to IB Gateway")
        else:
            logger.warning("IB Gateway unavailable – market data will use cache only")
            _ib_client = None

    except Exception as exc:
        logger.warning("IB connection failed (%s) – falling back to cache", exc)
        _ib_client = None
        _ib_connected = False

    return _ib_client


# ── FastMCP server ─────────────────────────────────────────────────────────────
mcp = FastMCP(
    "ib-trading",
    instructions=(
        "Tools for Interactive Brokers market data, portfolio management, and "
        "backtesting UK ETFs (VUSA, SSLN, SGLN, IWRD). "
        "Market data tools fall back to local parquet cache when IB Gateway is "
        "offline. Portfolio tools require a live IB connection on port 4001."
    ),
)


# ═══════════════════════════════════════════════════════════════════════════════
# Market Data
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_historical_data(
    symbol: str,
    duration_days: int = 365,
    bar_size: str = "1 day",
    currency: str = "GBP",
    exchange: str = "SMART",
) -> str:
    """
    Fetch historical OHLCV data for a single symbol.

    Tries IB Gateway first; automatically falls back to the local parquet cache
    if IB is unavailable.  Returns a JSON summary with row count, date range,
    available columns, and the last 10 rows.

    Args:
        symbol:        Ticker symbol (e.g. VUSA, SSLN, SGLN, IWRD, AAPL)
        duration_days: Calendar days of history to fetch (default: 365)
        bar_size:      IB bar-size string – "1 day", "1 hour", "5 mins", etc.
        currency:      Currency code (default: GBP for UK ETFs; use USD for US stocks)
        exchange:      Exchange routing (default: SMART)
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=duration_days)

    client = await _get_ib_client()
    df: Optional[pd.DataFrame] = None
    source = "live"

    if client is not None:
        try:
            df = await client.download_extended_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                bar_size=bar_size,
                currency=currency,
                exchange=exchange,
                sec_type="STK",
            )
        except Exception as exc:
            logger.warning("Live fetch failed for %s: %s", symbol, exc)
            df = None

    if df is None or df.empty:
        source = "cache"
        df = _load_best_cache(symbol)

    if df is None or df.empty:
        return json.dumps({
            "error": (
                f"No data found for '{symbol}'. "
                "IB Gateway is offline and no local cache exists for this symbol."
            )
        })

    # Trim to requested date range when loading from cache
    if isinstance(df.index, pd.DatetimeIndex):
        df = df.loc[df.index >= pd.Timestamp(start_date)]
    elif "date" in df.columns:
        df = df[df["date"] >= start_date]

    tail = df.tail(10).copy()
    if isinstance(tail.index, pd.DatetimeIndex):
        tail.index = tail.index.strftime("%Y-%m-%d")

    return json.dumps(
        {
            "symbol": symbol,
            "source": source,
            "rows": len(df),
            "start": _ts(df.index[0] if isinstance(df.index, pd.DatetimeIndex) else df["date"].iloc[0]),
            "end":   _ts(df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else df["date"].iloc[-1]),
            "columns": list(df.columns),
            "last_10_rows": tail.reset_index().to_dict(orient="records"),
        },
        default=str,
    )


@mcp.tool()
async def get_multiple_historical_data(
    symbols: List[str],
    duration_days: int = 365,
    bar_size: str = "1 day",
    currency: str = "GBP",
) -> str:
    """
    Fetch historical OHLCV data for multiple symbols in one call.

    Calls get_historical_data for each symbol and returns a combined JSON
    object mapping symbol → summary (shape, date range, last close).

    Args:
        symbols:       List of ticker symbols (e.g. ["VUSA", "SSLN", "SGLN", "IWRD"])
        duration_days: Calendar days of history to fetch (default: 365)
        bar_size:      IB bar-size string (default: "1 day")
        currency:      Currency code (default: GBP)
    """
    results: dict = {}
    for symbol in symbols:
        raw = await get_historical_data(
            symbol=symbol,
            duration_days=duration_days,
            bar_size=bar_size,
            currency=currency,
        )
        results[symbol] = json.loads(raw)
    return json.dumps(results, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def get_positions() -> str:
    """
    Get all current portfolio positions from IB.

    Returns a JSON list of open positions including symbol, quantity,
    market value, average cost, and unrealised / realised P&L.

    Requires a live IB connection.  Start IB Gateway Paper on port 4001.
    """
    client = await _get_ib_client()
    if client is None:
        return json.dumps({
            "error": "IB Gateway not available. Start IB Gateway Paper on port 4001 and retry."
        })

    try:
        positions = await client.get_positions()
        return json.dumps(
            [
                {
                    "symbol":        p.symbol,
                    "position":      p.position,
                    "market_price":  p.market_price,
                    "market_value":  p.market_value,
                    "average_cost":  p.average_cost,
                    "unrealized_pnl": p.unrealized_pnl,
                    "realized_pnl":  p.realized_pnl,
                    "account":       p.account,
                }
                for p in positions
            ],
            indent=2,
            default=str,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_account_summary() -> str:
    """
    Get account summary: net liquidation value, buying power, cash, and P&L.

    Returns a JSON object with the key account metrics from IB.

    Requires a live IB connection.  Start IB Gateway Paper on port 4001.
    """
    client = await _get_ib_client()
    if client is None:
        return json.dumps({
            "error": "IB Gateway not available. Start IB Gateway Paper on port 4001 and retry."
        })

    try:
        summary = await client.get_account_summary()
        return json.dumps(summary, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ═══════════════════════════════════════════════════════════════════════════════
# Backtesting
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool()
async def list_strategies() -> str:
    """
    List all available backtesting strategies with descriptions and parameters.

    Returns a JSON object mapping strategy_key → metadata (source, type,
    display name, description, parameters).
    """
    try:
        from strategies import STRATEGY_REGISTRY              # noqa: PLC0415
        from strategies.strategy_loader import StrategyLoader  # noqa: PLC0415

        result: dict = {}

        # Registry-based (hrp, equal_weight, trend_following)
        for key, meta in STRATEGY_REGISTRY.items():
            result[key] = {
                "source":       "registry",
                "display_name": meta.get("display_name", key),
                "description":  meta.get("description", ""),
                "parameters":   meta.get("default_params", {}),
            }

        # YAML-defined strategies (minimum_variance, risk_parity, momentum, etc.)
        loader = StrategyLoader()
        for kind in ("allocation", "composed"):
            try:
                for k, v in loader.list_strategies(kind).items():
                    if k not in result:
                        result[k] = {"source": "yaml", "type": kind, **v}
            except Exception:
                pass

        return json.dumps(result, indent=2, default=str)

    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def run_backtest(
    strategy: str,
    refresh: bool = False,
) -> str:
    """
    Run backtests for ALL available strategies and return results for the one
    you asked for.

    Uses scripts/run_backtest.py --all under the hood, which:
      - Reads market data from local cache (fast, no IB needed)
      - Falls back to fetching from IB only when cache is empty
      - Saves every strategy's results under results/strategies/<key>/

    This typically takes 60-120 seconds on first run (data fetch + computation)
    and around 10-30 seconds on subsequent runs (cache warm).

    Use get_backtest_results to read saved results without re-running.

    Args:
        strategy: Strategy key whose results to return after the run.
                  Common values: hrp_single, hrp_ward, trend_following,
                  equal_weight, minimum_variance, risk_parity, momentum.
        refresh:  Force fresh data from IB (default: False).
                  Requires a live IB connection.
    """
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "run_backtest.py"), "--all"]
    if refresh:
        cmd.append("--refresh")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            return json.dumps({
                "error":  f"Backtest script exited with code {proc.returncode}",
                "stderr": stderr.decode(errors="replace")[-3000:],
            })

        results = _read_strategy_results(strategy)
        if results is None:
            return json.dumps({
                "status":      "completed",
                "warning":     f"Run succeeded but no results found for '{strategy}'. Check the strategy key.",
                "stdout_tail": stdout.decode(errors="replace")[-1500:],
                "available":   _list_available_results(),
            })

        return json.dumps(
            {"status": "completed", "strategy": strategy, **results},
            indent=2,
            default=str,
        )

    except asyncio.TimeoutError:
        return json.dumps({"error": "Backtest timed out after 5 minutes"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


@mcp.tool()
async def get_backtest_results(strategy_key: str) -> str:
    """
    Read saved backtest results for a strategy without re-running the backtest.

    Returns metrics, portfolio value summary (first/last date and value),
    and strategy metadata.  Run run_backtest first if no results exist yet.

    Args:
        strategy_key: Strategy key (e.g. hrp_single, trend_following, equal_weight)
    """
    results = _read_strategy_results(strategy_key)
    if results is None:
        return json.dumps({
            "error":     f"No results found for '{strategy_key}'. Run run_backtest first.",
            "available": _list_available_results(),
        })

    return json.dumps({"strategy": strategy_key, **results}, indent=2, default=str)


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_best_cache(symbol: str) -> Optional[pd.DataFrame]:
    """
    Scan data/cache/ for parquet files matching *symbol* and load the
    largest one (most rows = most complete history).
    """
    cache_dir = PROJECT_ROOT / "data" / "cache"
    if not cache_dir.exists():
        return None

    candidates = sorted(
        cache_dir.glob(f"{symbol}_*.parquet"),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not candidates:
        return None

    try:
        return pd.read_parquet(candidates[0])
    except Exception as exc:
        logger.warning("Failed to load cache for %s: %s", symbol, exc)
        return None


def _read_strategy_results(strategy_key: str) -> Optional[dict]:
    """
    Read metrics.json, info.json, and a portfolio history summary from
    results/strategies/<strategy_key>/.
    """
    strat_dir = PROJECT_ROOT / "results" / "strategies" / strategy_key
    if not strat_dir.exists():
        return None

    result: dict = {}

    metrics_path = strat_dir / "metrics.json"
    if metrics_path.exists():
        result["metrics"] = json.loads(metrics_path.read_text())

    info_path = strat_dir / "info.json"
    if info_path.exists():
        result["info"] = json.loads(info_path.read_text())

    portfolio_path = strat_dir / "portfolio_history.json"
    if portfolio_path.exists():
        history = json.loads(portfolio_path.read_text())
        if history:
            first, last = history[0], history[-1]
            result["portfolio_summary"] = {
                "first_date":    first.get("date"),
                "last_date":     last.get("date"),
                "initial_value": first.get("total_value") or first.get("value"),
                "final_value":   last.get("total_value")  or last.get("value"),
                "data_points":   len(history),
            }

    return result if result else None


def _list_available_results() -> list:
    """Return strategy keys that have saved results in results/strategies/."""
    strategies_dir = PROJECT_ROOT / "results" / "strategies"
    if not strategies_dir.exists():
        return []
    return [p.name for p in sorted(strategies_dir.iterdir()) if p.is_dir()]


def _ts(val) -> str:
    """Convert a timestamp / date to an ISO-format string."""
    return val.isoformat() if hasattr(val, "isoformat") else str(val)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
