"""
Walk-forward analysis for strategy parameter optimization.

Splits historical data into rolling in-sample/out-of-sample windows.
For each window: optimizes parameters on in-sample, tests on out-of-sample.
Reports average out-of-sample performance and overfitting ratio.

Example:
    wfa = WalkForwardAnalysis(
        strategy_class=TrendFollowingStrategy,
        param_grid={
            'lookback_days': [252, 504],
            'half_life_days': [30, 60, 90]
        },
        in_sample_days=756,
        out_of_sample_days=252
    )
    results = wfa.run(underlying_assets, prices)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Any, Type

import pandas as pd
import numpy as np

from strategies.core import AllocationStrategy, Strategy
from .param_sweep import ParameterSweep

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardWindow:
    """Result from one walk-forward window."""
    window_index: int
    in_sample_start: pd.Timestamp
    in_sample_end: pd.Timestamp
    out_sample_start: pd.Timestamp
    out_sample_end: pd.Timestamp
    best_params: Dict[str, Any]
    in_sample_metric: float
    out_sample_metric: float


@dataclass
class WalkForwardResults:
    """Aggregate results from walk-forward analysis."""
    windows: List[WalkForwardWindow]
    target_metric: str
    avg_in_sample: float = 0.0
    avg_out_sample: float = 0.0
    overfitting_ratio: float = 0.0
    summary_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __post_init__(self):
        if self.windows:
            in_samples = [w.in_sample_metric for w in self.windows]
            out_samples = [w.out_sample_metric for w in self.windows]
            self.avg_in_sample = np.mean(in_samples)
            self.avg_out_sample = np.mean(out_samples)
            self.overfitting_ratio = (
                self.avg_in_sample / self.avg_out_sample
                if self.avg_out_sample != 0 else float('inf')
            )

            self.summary_df = pd.DataFrame([{
                'window': w.window_index,
                'in_sample': f"{w.in_sample_start.date()} to {w.in_sample_end.date()}",
                'out_sample': f"{w.out_sample_start.date()} to {w.out_sample_end.date()}",
                **{f'best_{k}': v for k, v in w.best_params.items()},
                f'in_sample_{self.target_metric}': w.in_sample_metric,
                f'out_sample_{self.target_metric}': w.out_sample_metric,
            } for w in self.windows])


class WalkForwardAnalysis:
    """
    Walk-forward optimization with rolling windows.

    Divides data into sequential windows:
    [in-sample | out-of-sample] -> [in-sample | out-of-sample] -> ...

    For each window:
    1. Run parameter sweep on in-sample period
    2. Select best parameters by target metric
    3. Test those parameters on out-of-sample period
    4. Record both in-sample and out-of-sample performance
    """

    def __init__(
        self,
        strategy_class: Type[AllocationStrategy],
        param_grid: Dict[str, List[Any]],
        in_sample_days: int = 756,
        out_of_sample_days: int = 252,
        metric: str = 'sharpe_ratio',
        initial_capital: float = 10000.0,
        transaction_cost_bps: float = 7.5,
        step_days: int = None
    ):
        """
        Args:
            strategy_class: Strategy class to optimize
            param_grid: Parameter grid for sweep
            in_sample_days: Number of trading days for in-sample (default: 756 = ~3 years)
            out_of_sample_days: Number of trading days for out-of-sample (default: 252 = ~1 year)
            metric: Target metric to optimize
            initial_capital: Starting capital
            transaction_cost_bps: Transaction costs
            step_days: Days to step forward between windows (default: out_of_sample_days)
        """
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.in_sample_days = in_sample_days
        self.out_of_sample_days = out_of_sample_days
        self.metric = metric
        self.initial_capital = initial_capital
        self.transaction_cost_bps = transaction_cost_bps
        self.step_days = step_days or out_of_sample_days

    def run(
        self,
        underlying: List[Strategy],
        prices: pd.DataFrame,
    ) -> WalkForwardResults:
        """
        Run walk-forward analysis.

        Args:
            underlying: List of asset strategies
            prices: Full historical price DataFrame

        Returns:
            WalkForwardResults with per-window and aggregate results
        """
        trading_days = prices.index
        total_needed = self.in_sample_days + self.out_of_sample_days

        if len(trading_days) < total_needed:
            raise ValueError(
                f"Need at least {total_needed} trading days, "
                f"have {len(trading_days)}"
            )

        windows = []
        window_idx = 0
        start_idx = 0

        while start_idx + total_needed <= len(trading_days):
            is_start = trading_days[start_idx]
            is_end = trading_days[start_idx + self.in_sample_days - 1]
            oos_start = trading_days[start_idx + self.in_sample_days]
            oos_end_idx = min(
                start_idx + total_needed - 1,
                len(trading_days) - 1
            )
            oos_end = trading_days[oos_end_idx]

            logger.info(
                f"\nWindow {window_idx + 1}: "
                f"IS={is_start.date()}-{is_end.date()}, "
                f"OOS={oos_start.date()}-{oos_end.date()}"
            )

            # Run parameter sweep on in-sample
            sweep = ParameterSweep(
                strategy_class=self.strategy_class,
                param_grid=self.param_grid,
                metric=self.metric,
                initial_capital=self.initial_capital,
                transaction_cost_bps=self.transaction_cost_bps
            )

            sweep_results = sweep.run(
                underlying=underlying,
                prices=prices,
                start_date=is_start,
                end_date=is_end,
                lookback_days=252
            )

            if sweep_results.empty:
                logger.warning(f"Window {window_idx + 1}: no valid results, skipping")
                start_idx += self.step_days
                window_idx += 1
                continue

            # Best params from in-sample
            best_row = sweep_results.iloc[0]
            param_keys = list(self.param_grid.keys())
            best_params = {k: best_row[k] for k in param_keys}
            is_metric_value = float(best_row[self.metric])

            logger.info(f"  Best IS params: {best_params} ({self.metric}={is_metric_value:.4f})")

            # Test best params on out-of-sample
            oos_sweep = ParameterSweep(
                strategy_class=self.strategy_class,
                param_grid={k: [v] for k, v in best_params.items()},
                metric=self.metric,
                initial_capital=self.initial_capital,
                transaction_cost_bps=self.transaction_cost_bps
            )

            oos_results = oos_sweep.run(
                underlying=underlying,
                prices=prices,
                start_date=oos_start,
                end_date=oos_end,
                lookback_days=252
            )

            if oos_results.empty:
                logger.warning(f"Window {window_idx + 1}: OOS test failed, skipping")
                start_idx += self.step_days
                window_idx += 1
                continue

            oos_metric_value = float(oos_results.iloc[0][self.metric])
            logger.info(f"  OOS {self.metric}={oos_metric_value:.4f}")

            windows.append(WalkForwardWindow(
                window_index=window_idx + 1,
                in_sample_start=is_start,
                in_sample_end=is_end,
                out_sample_start=oos_start,
                out_sample_end=oos_end,
                best_params=best_params,
                in_sample_metric=is_metric_value,
                out_sample_metric=oos_metric_value,
            ))

            start_idx += self.step_days
            window_idx += 1

        results = WalkForwardResults(
            windows=windows,
            target_metric=self.metric
        )

        logger.info(f"\nWalk-Forward Complete:")
        logger.info(f"  Windows: {len(windows)}")
        logger.info(f"  Avg In-Sample {self.metric}: {results.avg_in_sample:.4f}")
        logger.info(f"  Avg Out-of-Sample {self.metric}: {results.avg_out_sample:.4f}")
        logger.info(f"  Overfitting Ratio: {results.overfitting_ratio:.2f}x")

        return results
