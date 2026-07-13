#!/usr/bin/env python3
"""Meta-backtest the strategy-SELECTION rule itself (not any single strategy).

The selection process — "each quarter, pick the top-k strategies by trailing
Sharpe and hold them" — is itself a strategy with its own overfitting risk that
the per-strategy validation never measures. This walks that rule forward:

    for each quarter-end q:
        rank every strategy by Sharpe using ONLY data up to q
        pick the top-k; hold them equal-weighted over the next quarter
        record the realized equal-weighted return of that quarter
    chain the quarterly returns

and benchmarks it against (a) random k-picks and (b) holding everything. If the
selection rule barely beats random, our promotion process is noise-mining.

Reuses ``load_portfolio_values`` + ``summarize_performance`` only; deterministic
(seeded RNG). Writes ``results/meta_selection.json``. Read-only — never trades.

Usage:
    python scripts/meta_backtest_selection.py --k 5 --metric sharpe
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.metrics import summarize_performance  # noqa: E402
from backtesting.results_schema import (  # noqa: E402
    INDEX_FILE,
    load_portfolio_values,
)

logger = logging.getLogger(__name__)

RESULTS_DIR = Path("results")
OUT_PATH = RESULTS_DIR / "meta_selection.json"

_METRIC_KEY = {
    "sharpe": "sharpe_ratio",
    "total_return": "total_return",
    "cagr": "cagr",
}


# ---------------------------------------------------------------------------
# Pure engine
# ---------------------------------------------------------------------------
def _quarter_ends(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Quarter-end dates spanned by ``index`` (each <= last index date)."""
    if len(index) == 0:
        return []
    q = pd.date_range(index.min(), index.max(), freq="QE")
    return [t for t in q if t >= index.min()]


def _asof(series: pd.Series, when: pd.Timestamp):
    """Last value at or before ``when`` (None if series starts after)."""
    s = series[series.index <= when]
    return None if s.empty else float(s.iloc[-1])


def _quarter_return(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp):
    """Return of a value series over (start, end] using as-of lookups."""
    v0, v1 = _asof(series, start), _asof(series, end)
    if v0 is None or v1 is None or v0 <= 0:
        return None
    return v1 / v0 - 1.0


def _rank_metric(series: pd.Series, asof: pd.Timestamp, metric_key: str):
    """Selection metric from a strategy's history truncated at ``asof``."""
    hist = series[series.index <= asof]
    if len(hist) < 30:
        return None
    val = summarize_performance(hist).get(metric_key)
    return None if val is None or not np.isfinite(val) else float(val)


def _chain(quarter_returns: list[float]) -> dict:
    """Compound a list of quarterly returns into a metrics block."""
    rets = [r for r in quarter_returns if r is not None]
    if not rets:
        return {"total_return": None, "sharpe": None, "cagr": None, "n_quarters": 0}
    curve = pd.Series(np.cumprod([1.0 + r for r in rets]))
    perf = summarize_performance(curve)  # quarterly spacing -> ppy≈4 inferred
    return {
        "total_return": float(curve.iloc[-1] - 1.0),
        "sharpe": perf.get("sharpe_ratio"),
        "cagr": perf.get("cagr"),
        "n_quarters": len(rets),
        "quarterly_returns": [round(r, 6) for r in rets],
    }


def run_meta_backtest(
    histories: dict[str, pd.Series],
    k: int = 5,
    metric: str = "sharpe",
    n_random: int = 200,
    seed: int = 12345,
) -> dict:
    """Walk-forward the top-k selection rule vs random picks and hold-all."""
    metric_key = _METRIC_KEY.get(metric, "sharpe_ratio")
    histories = {
        kk: v.sort_index()
        for kk, v in histories.items()
        if v is not None and len(v) > 30
    }
    if len(histories) <= k:
        raise ValueError(f"need > k={k} strategies with history, got {len(histories)}")

    all_dates = pd.DatetimeIndex(
        sorted({d for s in histories.values() for d in s.index})
    )
    quarters = _quarter_ends(all_dates)
    if len(quarters) < 3:
        raise ValueError("not enough quarterly history for a walk-forward")

    keys = sorted(histories)  # deterministic order
    rng = np.random.default_rng(seed)

    sel_q, hold_q = [], []
    rand_q = [[] for _ in range(n_random)]
    used_quarters = []

    for q_start, q_end in zip(quarters[:-1], quarters[1:]):
        # Rank using only data up to the quarter start (no look-ahead).
        scored = [(kk, _rank_metric(histories[kk], q_start, metric_key)) for kk in keys]
        eligible = [(kk, sc) for kk, sc in scored if sc is not None]
        # A quarter needs a realized forward return for every held strategy.
        eligible = [
            (kk, sc)
            for kk, sc in eligible
            if _quarter_return(histories[kk], q_start, q_end) is not None
        ]
        if len(eligible) <= k:
            continue
        used_quarters.append(q_end.strftime("%Y-%m-%d"))

        ranked = [kk for kk, _ in sorted(eligible, key=lambda x: x[1], reverse=True)]
        pool = [kk for kk, _ in eligible]

        def eq_return(selected):
            rs = [_quarter_return(histories[kk], q_start, q_end) for kk in selected]
            return float(np.mean(rs))

        sel_q.append(eq_return(ranked[:k]))
        hold_q.append(eq_return(pool))
        for i in range(n_random):
            pick = rng.choice(pool, size=k, replace=False)
            rand_q[i].append(eq_return(list(pick)))

    selection = _chain(sel_q)
    hold_all = _chain(hold_q)
    rand_totals = [np.prod([1.0 + r for r in row]) - 1.0 for row in rand_q if row]
    random_block = {
        "mean_total_return": float(np.mean(rand_totals)) if rand_totals else None,
        "std_total_return": float(np.std(rand_totals)) if rand_totals else None,
        "p05_total_return": (
            float(np.percentile(rand_totals, 5)) if rand_totals else None
        ),
        "p95_total_return": (
            float(np.percentile(rand_totals, 95)) if rand_totals else None
        ),
        "n_samples": len(rand_totals),
    }
    # Selection percentile within the random distribution — the honesty check.
    sel_total = selection.get("total_return")
    percentile = (
        float((np.array(rand_totals) < sel_total).mean() * 100.0)
        if rand_totals and sel_total is not None
        else None
    )

    return {
        "params": {
            "k": k,
            "metric": metric,
            "n_random": n_random,
            "seed": seed,
            "n_strategies": len(histories),
            "quarters": used_quarters,
        },
        "selection": selection,
        "hold_all": hold_all,
        "random": random_block,
        "selection_percentile_vs_random": percentile,
    }


# ---------------------------------------------------------------------------
# Loading + CLI
# ---------------------------------------------------------------------------
def _load_histories(results_dir: Path) -> dict[str, pd.Series]:
    index_path = results_dir / INDEX_FILE
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        keys = list((index.get("strategies") or {}).keys()) or [
            s.get("key") for s in index.get("strategies", [])
        ]
    else:
        keys = [p.name for p in (results_dir / "strategies").iterdir() if p.is_dir()]
    out: dict[str, pd.Series] = {}
    for key in keys:
        if not key:
            continue
        try:
            s = load_portfolio_values(results_dir, key)
        except Exception:
            continue
        if s is not None and len(s) > 30:
            out[key] = s
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--k", type=int, default=5, help="Top-k strategies held per quarter."
    )
    parser.add_argument("--metric", choices=list(_METRIC_KEY), default="sharpe")
    parser.add_argument("--n-random", type=int, default=200)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    histories = _load_histories(RESULTS_DIR)
    logger.info(f"Loaded {len(histories)} strategy histories")
    result = run_meta_backtest(
        histories, k=args.k, metric=args.metric, n_random=args.n_random, seed=args.seed
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    sel = result["selection"]
    rnd = result["random"]
    logger.info(
        f"Selection total return {sel['total_return']:.1%} vs random mean "
        f"{rnd['mean_total_return']:.1%} "
        f"(percentile {result['selection_percentile_vs_random']:.0f}); "
        f"hold-all {result['hold_all']['total_return']:.1%} -> {OUT_PATH}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
