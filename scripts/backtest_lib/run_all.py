"""Batch runner: execute every available strategy definition in one pass.

Each strategy is built with its OWN loader and backtested in isolation, then
writes its own results/strategies/<key>/ files downstream — so the batch both
(a) parallelises across a process pool and (b) is deterministic regardless of
worker count. Building every strategy through one shared StrategyLoader (the
old behaviour) let strategies that share an underlying share mutable objects,
so one backtest contaminated another's result and the batch was order-
dependent. Fresh-per-strategy builds remove that coupling.

The sequential save loop (which merges strategies_index.json) stays in the
parent; cross-strategy steps (SPA, group/composed PBO) run later, unaffected.
"""

import logging
import os
from concurrent.futures import ProcessPoolExecutor

from strategies import prune_missing_assets
from strategies.strategy_loader import StrategyLoader
from backtesting import BacktestEngine
from backtesting.runner import run_single_backtest
from backtesting.results_io import serialize_backtest_results
from analytics.stress_testing import StressTestReport, StressTester

from .config import (
    INITIAL_CAPITAL,
    LOOKBACK_DAYS,
    REBALANCE_FREQUENCY,
    TRANSACTION_COST_BPS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker state (one set per process; populated by the pool initializer so the
# large price panel is materialised once per worker, not pickled per task).
# ---------------------------------------------------------------------------
_W_PRICES = None
_W_ENGINE_KWARGS = None
_W_AVAIL = None
_W_START = None
_W_END = None
_W_SCENARIO = False


def _init_worker(prices, engine_kwargs, backtest_start, backtest_end, scenario_removal):
    """Initialise per-process worker state (also used for the serial path)."""
    global _W_PRICES, _W_ENGINE_KWARGS, _W_AVAIL, _W_START, _W_END, _W_SCENARIO
    _W_PRICES = prices
    _W_ENGINE_KWARGS = engine_kwargs
    _W_AVAIL = set(prices.columns)
    _W_START = backtest_start
    _W_END = backtest_end
    _W_SCENARIO = scenario_removal


def _build_fresh(strategy_key):
    """Build a strategy and its info dict from a private loader (no sharing).

    Mirrors strategies.catalog.get_all_available_strategies' per-key build so
    results are identical to a single-strategy run.
    """
    loader = StrategyLoader()
    strategy = loader.build_strategy(strategy_key)
    definition = loader.load_definition(strategy_key)
    info = {
        "key": strategy_key,
        "type": definition.get("type"),
        "class": definition.get("class"),
        "description": definition.get("description", ""),
        "parameters": definition.get("parameters", {}),
    }
    return strategy, info


def _backtest_one(strategy_key):
    """Backtest + serialize a single strategy in a worker process.

    Returns ``(strategy_key, serialized_or_None, error_or_None)``. Never raises
    — a failing strategy is reported so the batch continues.
    """
    try:
        strategy, strategy_info = _build_fresh(strategy_key)
        strategy = prune_missing_assets(strategy, _W_AVAIL)
        if strategy is None:
            return strategy_key, None, "no assets with price data remain"

        engine = BacktestEngine(**_W_ENGINE_KWARGS)
        results = run_single_backtest(
            strategy,
            _W_PRICES,
            _W_START,
            _W_END,
            engine,
            default_lookback_days=LOOKBACK_DAYS,
        )
        serialized = serialize_backtest_results(results, strategy_key, strategy_info)

        # Rerun-mode leave-one-crisis-out needs the live strategy/engine/prices,
        # which only exist here. Stash the report for the parent's save loop.
        if _W_SCENARIO:
            try:
                values = results.portfolio_history["total_value"]
                name = strategy_info.get("name", strategy_key)
                tester = StressTester(values, name)
                crisis_metrics = [tester._analyse_crisis(c) for c in tester.crises]
                scenario = tester.run_leave_one_out(
                    mode="rerun",
                    strategy=strategy,
                    prices=_W_PRICES,
                    engine=engine,
                    backtest_start=_W_START,
                    backtest_end=_W_END,
                    default_lookback_days=LOOKBACK_DAYS,
                )
                report = StressTestReport(
                    strategy_name=name,
                    crisis_metrics=crisis_metrics,
                    scenario_removal=scenario,
                    scenario_removal_mode="rerun",
                )
                serialized["_stress_report"] = report.to_dict()
            except Exception as exc:  # noqa: BLE001 — scenario removal is best-effort
                logger.warning(
                    f"  Scenario-removal rerun failed for {strategy_key}: {exc}"
                )

        return strategy_key, serialized, None
    except Exception as exc:  # noqa: BLE001 — one bad strategy must not kill the batch
        return strategy_key, None, f"{type(exc).__name__}: {exc}"


def _all_strategy_keys() -> list:
    """List every buildable definition key without building the strategies."""
    loader = StrategyLoader()
    keys = []
    for kind in ("allocation", "composed", "portfolio"):
        keys.extend(loader.list_strategies(kind).keys())
    return sorted(keys)


def _resolve_jobs(requested, n_tasks) -> int:
    """Map the --jobs value to an actual worker count."""
    if requested and requested > 0:
        return max(1, min(requested, n_tasks))
    # auto: leave one core free for the OS / parent
    return max(1, min((os.cpu_count() or 2) - 1, n_tasks))


async def run_all_strategies(args, prices, backtest_start, backtest_end):
    """
    Run all available strategies and generate comprehensive results.

    Backtests run across a process pool (``--jobs``); the returned mapping is
    ``{strategy_key: serialized_dict}`` — identical whatever the worker count.
    """
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING ALL AVAILABLE STRATEGIES")
    logger.info("=" * 60)

    keys = _all_strategy_keys()
    logger.info(f"Found {len(keys)} available strategies")

    engine_kwargs = dict(
        initial_capital=INITIAL_CAPITAL,
        transaction_cost_bps=TRANSACTION_COST_BPS,
        rebalance_frequency=REBALANCE_FREQUENCY,
    )
    scenario_removal = bool(getattr(args, "scenario_removal", False))
    init_args = (prices, engine_kwargs, backtest_start, backtest_end, scenario_removal)
    jobs = _resolve_jobs(getattr(args, "jobs", 0), len(keys))

    all_results = {}

    def _collect(result):
        strategy_key, serialized, error = result
        if error is not None:
            logger.error(f"  Failed to run {strategy_key}: {error}")
            return
        all_results[strategy_key] = serialized

    if jobs == 1:
        logger.info("Backtesting serially (--jobs 1)")
        _init_worker(*init_args)
        for key in keys:
            _collect(_backtest_one(key))
    else:
        logger.info(f"Backtesting across {jobs} worker processes")
        with ProcessPoolExecutor(
            max_workers=jobs, initializer=_init_worker, initargs=init_args
        ) as executor:
            for result in executor.map(_backtest_one, keys):
                _collect(result)

    logger.info(f"\nBacktested {len(all_results)}/{len(keys)} strategies")
    return all_results
