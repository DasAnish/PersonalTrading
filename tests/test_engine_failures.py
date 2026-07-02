"""
Tests for BacktestEngine's handling of strategy failures during rebalancing.

Regression coverage for the fix that replaced a bare `except Exception:
continue` with specific exception handling plus `failed_rebalances` tracking
on BacktestResults.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import data as data_pkg
from backtesting.engine import BacktestEngine
from strategies.core import DataRequirements, Strategy, StrategyContext

SYMBOLS = ["VUSA", "SSLN"]


def make_prices(n_days: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_days)
    returns = rng.normal(0.0003, 0.01, size=(n_days, len(SYMBOLS)))
    prices = 100 * np.cumprod(1 + returns, axis=0)
    return pd.DataFrame(prices, index=dates, columns=SYMBOLS)


class FlakyStrategy(Strategy):
    """Equal-weight strategy that raises ValueError on one specific rebalance date."""

    def __init__(self, fail_on_date: pd.Timestamp):
        super().__init__(name="Flaky")
        self.fail_on_date = fail_on_date

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        if context.current_date == self.fail_on_date:
            raise ValueError(f"Simulated failure at {self.fail_on_date}")
        n = len(SYMBOLS)
        return pd.Series([1.0 / n] * n, index=SYMBOLS)

    def get_price_timeseries(self, context: StrategyContext) -> pd.Series:
        return context.prices.mean(axis=1)

    def get_data_requirements(self) -> DataRequirements:
        return DataRequirements(symbols=SYMBOLS, lookback_days=30, currency="GBP")


class FakeMarketDataService:
    """Minimal stand-in for MarketDataService, backed by pre-built prices."""

    def __init__(self, prices: pd.DataFrame):
        self.prices = prices

    async def fetch_data(self, requirements, start_date, end_date, refresh=False):
        return self.prices

    def get_context_for_date(self, all_data, current_date, lookback_days):
        lookback_start = current_date - timedelta(days=lookback_days)
        sliced = all_data[
            (all_data.index >= lookback_start) & (all_data.index <= current_date)
        ]
        return StrategyContext(
            current_date=current_date,
            lookback_start=lookback_start,
            prices=sliced,
        )


async def test_failed_rebalance_is_tracked_and_backtest_completes(monkeypatch):
    prices = make_prices()
    fake_mds = FakeMarketDataService(prices)
    monkeypatch.setattr(data_pkg, "get_market_data", lambda: fake_mds)

    start_date = prices.index[60]
    end_date = prices.index[-1]

    engine = BacktestEngine(
        initial_capital=10_000, transaction_cost_bps=7.5, rebalance_frequency="monthly"
    )

    rebalance_dates = engine._generate_rebalance_dates(
        start_date, end_date, prices.index
    )
    assert len(rebalance_dates) >= 2, "Need at least 2 rebalance dates for this test"
    fail_date = rebalance_dates[1]

    strategy = FlakyStrategy(fail_on_date=fail_date)

    results = await engine.run_backtest(
        strategy=strategy, start_date=start_date, end_date=end_date
    )

    assert fail_date in results.failed_rebalances
    assert len(results.failed_rebalances) == 1
    # Backtest still completes and records the other (successful) rebalances
    assert len(results.portfolio_history) >= 1
