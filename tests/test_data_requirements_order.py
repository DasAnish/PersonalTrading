"""Regression guard: DataRequirements.aggregate_with must dedupe symbols in a
deterministic, order-preserving way.

The original list(set(...)) ordered symbols by PYTHONHASHSEED, permuting each
strategy's price panel / covariance matrix and making the --all backtest
non-reproducible run-to-run. See fix in strategies/core.py aggregate_with.
"""

from strategies.core import DataRequirements


def _req(symbols):
    return DataRequirements(symbols=symbols, lookback_days=10)


def test_aggregate_preserves_first_seen_order():
    a = _req(["VUSA", "SSLN", "SGLN"])
    b = _req(["SGLN", "IWRD", "VUSA"])
    out = a.aggregate_with(b)
    # First-seen order, duplicates dropped (SGLN/VUSA already present).
    assert out.symbols == ["VUSA", "SSLN", "SGLN", "IWRD"]


def test_aggregate_is_order_stable_regardless_of_input_hashing():
    # Many distinct string symbols: a set-based dedupe would reorder these
    # under a different PYTHONHASHSEED; dict.fromkeys never does.
    left = [f"SYM{i}" for i in range(20)]
    right = [f"SYM{i}" for i in range(10, 30)]
    out = _req(left).aggregate_with(_req(right))
    expected = left + [s for s in right if s not in set(left)]
    assert out.symbols == expected


def test_aggregate_takes_max_lookback():
    a = DataRequirements(symbols=["A"], lookback_days=50)
    b = DataRequirements(symbols=["B"], lookback_days=250)
    assert a.aggregate_with(b).lookback_days == 250
