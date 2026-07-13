"""Pre-registration of live strategies + kill-criteria evaluation (pure module).

Registering a strategy freezes the backtest metrics it was promoted on and the
kill criteria it must keep honouring, BEFORE out-of-sample evidence accrues.
The nightly then compares realized drawdown (from the live NAV history) against
that frozen envelope so a strategy that blows past its backtested risk is
flagged loudly instead of silently riding a drawdown.

Store: ``live_tracking/registrations/<strategy>.json`` (gitignored)::

    {"strategy": "hrp_ward", "registered_at": "2026-07-13T09:00:00",
     "backtest": {"sharpe": 1.3, "max_drawdown": -0.18, "cagr": 0.11,
                  "metrics_version": 2, "data_end": "2026-07-10"},
     "kill_criteria": {"realized_dd_multiple": 1.5, "portfolio_dd_limit": 0.30},
     "review_date": "2026-10-13"}

Pure: no IB / Flask imports. The nightly step (scripts/check_registrations.py)
reads the live CSVs and feeds series in here.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

REGISTRATIONS_DIR = Path("live_tracking") / "registrations"

DEFAULT_KILL_CRITERIA = {
    "realized_dd_multiple": 1.5,  # realized DD may reach 1.5x the backtested DD
    "portfolio_dd_limit": 0.30,  # absolute portfolio DD kill level (30%)
}

_BACKTEST_KEYS = ("sharpe", "max_drawdown", "cagr", "metrics_version", "data_end")


# ---------------------------------------------------------------------------
# Store I/O
# ---------------------------------------------------------------------------
def _dir(path_dir: Path = None) -> Path:
    return Path(path_dir) if path_dir is not None else REGISTRATIONS_DIR


def _reg_path(strategy: str, path_dir: Path = None) -> Path:
    return _dir(path_dir) / f"{strategy}.json"


def _atomic_write(data: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def backtest_block_from_metrics(metrics: dict) -> dict:
    """Extract the frozen backtest block from a strategy's metrics.json dict."""
    return {
        "sharpe": metrics.get("sharpe_ratio", metrics.get("sharpe")),
        "max_drawdown": metrics.get("max_drawdown"),
        "cagr": metrics.get("cagr"),
        "metrics_version": metrics.get("metrics_version"),
        "data_end": metrics.get("data_end"),
    }


def register(
    strategy: str,
    backtest: dict,
    kill_criteria: dict = None,
    review_date: str = None,
    registered_at: str = None,
    path_dir: Path = None,
) -> dict:
    """Freeze a strategy's registration. Overwrites any existing file."""
    if not strategy or not str(strategy).strip():
        raise ValueError("strategy must be a non-empty string")
    entry = {
        "strategy": strategy,
        "registered_at": registered_at or datetime.now().isoformat(timespec="seconds"),
        "backtest": {k: backtest.get(k) for k in _BACKTEST_KEYS},
        "kill_criteria": {**DEFAULT_KILL_CRITERIA, **(kill_criteria or {})},
        "review_date": review_date,
    }
    _atomic_write(entry, _reg_path(strategy, path_dir))
    return entry


def load_registration(strategy: str, path_dir: Path = None) -> Optional[dict]:
    path = _reg_path(strategy, path_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_registrations(path_dir: Path = None) -> List[dict]:
    directory = _dir(path_dir)
    if not directory.exists():
        return []
    out = []
    for p in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def remove_registration(strategy: str, path_dir: Path = None) -> bool:
    path = _reg_path(strategy, path_dir)
    if path.exists():
        path.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def max_drawdown(series: pd.Series) -> float:
    """Most negative peak-to-trough drawdown of a value series (<= 0.0)."""
    if series is None or len(series) < 2:
        return 0.0
    s = series.astype(float)
    running_max = s.cummax()
    dd = (s - running_max) / running_max
    return float(dd.min())


def _review_due(review_date: Optional[str], today: date) -> bool:
    if not review_date:
        return False
    try:
        return date.fromisoformat(str(review_date)[:10]) <= today
    except ValueError:
        return False


def evaluate(
    registration: dict,
    slice_nav: Optional[pd.Series],
    portfolio_nav: Optional[pd.Series],
    today: date = None,
) -> dict:
    """Grade a registration against realized live drawdowns.

    ``slice_nav`` = this strategy's live slice value series; ``portfolio_nav`` =
    whole-account NAV series. Status is ``breach`` if realized slice DD exceeds
    ``realized_dd_multiple`` x the backtested max DD, or portfolio DD exceeds
    the absolute ``portfolio_dd_limit``; else ``review_due`` if past review
    date; else ``ok``.
    """
    today = today or date.today()
    kc = {**DEFAULT_KILL_CRITERIA, **registration.get("kill_criteria", {})}
    bt = registration.get("backtest", {})

    realized_dd = max_drawdown(slice_nav) if slice_nav is not None else 0.0
    portfolio_dd = max_drawdown(portfolio_nav) if portfolio_nav is not None else 0.0

    bt_dd = bt.get("max_drawdown")
    envelope_dd = None
    if bt_dd is not None:
        # Backtested DD is negative; the tolerated envelope scales its magnitude.
        envelope_dd = -abs(float(bt_dd)) * float(kc["realized_dd_multiple"])

    reasons = []
    if envelope_dd is not None and realized_dd < envelope_dd:
        reasons.append(f"slice DD {realized_dd:.1%} beyond envelope {envelope_dd:.1%}")
    if portfolio_dd < -abs(float(kc["portfolio_dd_limit"])):
        reasons.append(
            f"portfolio DD {portfolio_dd:.1%} beyond limit "
            f"{-abs(float(kc['portfolio_dd_limit'])):.1%}"
        )

    if reasons:
        status = "breach"
    elif _review_due(registration.get("review_date"), today):
        status = "review_due"
    else:
        status = "ok"

    return {
        "status": status,
        "realized_dd": round(realized_dd, 6),
        "portfolio_dd": round(portfolio_dd, 6),
        "envelope_dd": round(envelope_dd, 6) if envelope_dd is not None else None,
        "reasons": reasons,
        "review_date": registration.get("review_date"),
    }


def evaluate_all(
    registrations: List[dict],
    slice_navs: Dict[str, pd.Series],
    portfolio_nav: Optional[pd.Series],
    today: date = None,
) -> Dict[str, dict]:
    """Evaluate every registration; returns ``{strategy: status_dict}``."""
    out: Dict[str, dict] = {}
    for reg in registrations:
        strat = reg.get("strategy")
        if not strat:
            continue
        out[strat] = evaluate(reg, slice_navs.get(strat), portfolio_nav, today)
    return out
