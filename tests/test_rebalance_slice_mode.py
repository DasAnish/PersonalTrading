"""Tests for the CLI slice-rebalance mode (scripts/rebalance_report.py --strategy-slice)."""

import json

import pytest

import analytics.ledger as ledger_mod
import scripts.rebalance_report as rr


@pytest.fixture
def slice_ledger(tmp_path, monkeypatch):
    """A ledger with one funded, partly-invested slice; cache priced via stubs."""
    path = tmp_path / "ledger.json"
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", path)
    ledger_mod.append_event(
        {
            "strategy": "hrp_ward",
            "trade_date": "2026-01-05",
            "external_cash_delta": 2000.0,
            "fills": [{"symbol": "VUSA", "shares_delta": 10.0, "price": 100.0}],
        }
    )
    # Cache prices + target weights come through these seams.
    monkeypatch.setattr(rr, "load_price_units", lambda: {})
    monkeypatch.setattr(
        rr,
        "close_price_base",
        lambda sym, units=None: {"VUSA": 100.0, "VWRL": 50.0}[sym],
    )
    monkeypatch.setattr(
        rr, "latest_target_weights", lambda key: {"VUSA": 0.5, "VWRL": 0.5}
    )
    return path


def _run(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["rebalance_report.py", *argv])
    rr.main()


def test_slice_mode_uses_ledger_holdings_and_cash(slice_ledger, monkeypatch, capsys):
    _run(monkeypatch, ["--strategy-slice", "hrp_ward", "--json-out"])
    out = capsys.readouterr().out
    assert "Slice: hrp_ward" in out
    # Slice cash = 2000 funding - 10*100 buy = 1000.
    assert "Slice cash (from ledger): 1,000.00" in out

    payload = json.loads(out[out.index("{") :])
    # Portfolio value = 10 VUSA @100 (1000) + 1000 cash = 2000.
    assert payload["total_portfolio_value"] == pytest.approx(2000.0)
    syms = {e["symbol"] for e in payload["entries"]}
    assert syms == {"VUSA", "VWRL"}


def test_slice_mode_budget_adds_investable_cash(slice_ledger, monkeypatch, capsys):
    _run(monkeypatch, ["--strategy-slice", "hrp_ward", "--budget", "500", "--json-out"])
    out = capsys.readouterr().out
    payload = json.loads(out[out.index("{") :])
    # 1000 holdings + 1000 slice cash + 500 budget = 2500.
    assert payload["total_portfolio_value"] == pytest.approx(2500.0)


def test_slice_mode_missing_weights_exits(slice_ledger, monkeypatch):
    monkeypatch.setattr(rr, "latest_target_weights", lambda key: {})
    with pytest.raises(SystemExit):
        _run(monkeypatch, ["--strategy-slice", "hrp_ward"])
