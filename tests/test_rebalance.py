"""
Tests for analytics/rebalance.py — pure rebalance-delta computation.

No IB imports, no network, no orders: compute_rebalance_plan() is a plain
function over dicts. These tests cover the edge cases called out in
plan/phase-05-reporting.md: weights that don't sum to 1, a symbol fully
exited, a new symbol bought from zero, a zero/missing price guard, and
totals consistency.
"""

import pytest

from analytics.rebalance import (
    DEFAULT_HOLD_THRESHOLD,
    RebalanceEntry,
    RebalancePlan,
    compute_rebalance_plan,
)


def _entry(plan: RebalancePlan, symbol: str) -> RebalanceEntry:
    for e in plan.entries:
        if e.symbol == symbol:
            return e
    raise AssertionError(f"No entry for {symbol}")


def test_weights_already_sum_to_one_are_not_normalized():
    plan = compute_rebalance_plan(
        positions={"A": 10, "B": 10},
        prices={"A": 100.0, "B": 100.0},
        target_weights={"A": 0.5, "B": 0.5},
        cash=0.0,
    )
    assert plan.weights_normalized is False
    assert plan.notes == []


def test_weights_not_summing_to_one_are_normalized():
    plan = compute_rebalance_plan(
        positions={"A": 10},
        prices={"A": 100.0},
        # Sums to 0.8, not 1.0.
        target_weights={"A": 0.4, "B": 0.4},
        cash=0.0,
    )
    assert plan.weights_normalized is True
    assert any("normalized" in n for n in plan.notes)

    a = _entry(plan, "A")
    b = _entry(plan, "B")
    # After normalization, 0.4/0.8 = 0.5 each.
    assert a.target_weight == pytest.approx(0.5)
    assert b.target_weight == pytest.approx(0.5)


def test_weights_summing_to_zero_cannot_normalize():
    plan = compute_rebalance_plan(
        positions={"A": 10},
        prices={"A": 100.0},
        target_weights={"A": 0.0, "B": 0.0},
        cash=0.0,
    )
    assert plan.weights_normalized is False
    assert any("unable to normalize" in n for n in plan.notes)
    assert _entry(plan, "A").target_weight == 0.0
    assert _entry(plan, "B").target_weight == 0.0


def test_symbol_fully_exited_is_a_sell_with_delta_equal_to_negative_current_value():
    # B is held but has no target weight -> full exit.
    plan = compute_rebalance_plan(
        positions={"A": 10, "B": 20},
        prices={"A": 100.0, "B": 50.0},
        target_weights={"A": 1.0},
        cash=0.0,
    )
    b = _entry(plan, "B")
    assert b.direction == "SELL"
    assert b.target_weight == pytest.approx(0.0)
    assert b.target_value == pytest.approx(0.0)
    assert b.current_value == pytest.approx(20 * 50.0)
    assert b.delta_value == pytest.approx(-b.current_value)


def test_new_symbol_buys_from_zero():
    # C has a target weight but is not currently held.
    plan = compute_rebalance_plan(
        positions={"A": 10},
        prices={"A": 100.0, "C": 25.0},
        target_weights={"A": 0.5, "C": 0.5},
        cash=0.0,
    )
    c = _entry(plan, "C")
    assert c.current_shares == 0.0
    assert c.current_value == pytest.approx(0.0)
    assert c.direction == "BUY"
    assert c.target_value > 0
    assert c.delta_value == pytest.approx(c.target_value)
    assert c.est_shares == pytest.approx(c.target_value / 25.0)


def test_zero_price_symbol_is_skipped_not_crashing():
    plan = compute_rebalance_plan(
        positions={"A": 10, "Z": 5},
        prices={"A": 100.0, "Z": 0.0},
        target_weights={"A": 0.5, "Z": 0.5},
        cash=0.0,
    )
    z = _entry(plan, "Z")
    assert z.skipped is True
    assert z.direction == "HOLD"
    assert z.note is not None
    assert z.current_value == 0.0
    # Skipped symbol's (unknown) value is excluded from the portfolio total.
    assert plan.total_portfolio_value == pytest.approx(1000.0)


def test_missing_price_symbol_is_skipped_not_crashing():
    plan = compute_rebalance_plan(
        positions={"A": 10, "NoPrice": 5},
        prices={"A": 100.0},  # NoPrice has no entry at all
        target_weights={"A": 1.0},
        cash=0.0,
    )
    entry = _entry(plan, "NoPrice")
    assert entry.skipped is True
    assert entry.direction == "HOLD"


def test_negative_price_symbol_is_skipped_not_crashing():
    plan = compute_rebalance_plan(
        positions={"A": 10, "Bad": 5},
        prices={"A": 100.0, "Bad": -10.0},
        target_weights={"A": 1.0},
        cash=0.0,
    )
    entry = _entry(plan, "Bad")
    assert entry.skipped is True


def test_totals_consistent_sum_of_target_value_equals_total_portfolio_value():
    plan = compute_rebalance_plan(
        positions={"A": 10, "B": 5},
        prices={"A": 100.0, "B": 200.0},
        target_weights={"A": 0.3, "B": 0.7},
        cash=500.0,
    )
    total_target_value = sum(e.target_value for e in plan.entries if not e.skipped)
    assert total_target_value == pytest.approx(plan.total_portfolio_value)

    # Portfolio value = cash + sum of current holding values.
    expected_total = 500.0 + (10 * 100.0) + (5 * 200.0)
    assert plan.total_portfolio_value == pytest.approx(expected_total)


def test_total_turnover_is_sum_of_absolute_deltas():
    plan = compute_rebalance_plan(
        positions={"A": 10, "B": 5},
        prices={"A": 100.0, "B": 200.0},
        target_weights={"A": 0.3, "B": 0.7},
        cash=0.0,
    )
    expected_turnover = sum(abs(e.delta_value) for e in plan.entries if not e.skipped)
    assert plan.total_turnover == pytest.approx(expected_turnover)


def test_direction_hold_below_threshold():
    # A already sits almost exactly at target weight -> HOLD, not BUY/SELL.
    plan = compute_rebalance_plan(
        positions={"A": 100},
        prices={"A": 100.0},
        target_weights={"A": 1.0},
        cash=0.0,
        hold_threshold=DEFAULT_HOLD_THRESHOLD,
    )
    a = _entry(plan, "A")
    assert a.delta_weight == pytest.approx(0.0)
    assert a.direction == "HOLD"


def test_direction_buy_and_sell_above_threshold():
    plan = compute_rebalance_plan(
        positions={"A": 100, "B": 100},
        prices={"A": 100.0, "B": 100.0},
        target_weights={"A": 0.8, "B": 0.2},
        cash=0.0,
    )
    a = _entry(plan, "A")
    b = _entry(plan, "B")
    assert a.direction == "BUY"
    assert b.direction == "SELL"


def test_hold_threshold_zero_disables_hold_for_any_nonzero_delta():
    plan = compute_rebalance_plan(
        positions={"A": 100},
        prices={"A": 100.0},
        # Tiny non-zero delta.
        target_weights={"A": 0.9999999},
        cash=0.0,
        hold_threshold=0.0,
    )
    a = _entry(plan, "A")
    assert a.direction in ("BUY", "SELL")


def test_empty_inputs_return_empty_plan():
    plan = compute_rebalance_plan(
        positions={}, prices={}, target_weights={}, cash=100.0
    )
    assert plan.entries == []
    assert plan.total_portfolio_value == pytest.approx(100.0)
    assert plan.total_turnover == pytest.approx(0.0)


def test_cash_is_included_in_total_portfolio_value():
    plan = compute_rebalance_plan(
        positions={"A": 10},
        prices={"A": 100.0},
        target_weights={"A": 1.0},
        cash=250.0,
    )
    assert plan.total_portfolio_value == pytest.approx(10 * 100.0 + 250.0)
    assert plan.cash == pytest.approx(250.0)
