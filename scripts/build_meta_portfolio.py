#!/usr/bin/env python3
"""
Blend the strategy library into one candidate live portfolio.

The library has ~183 backtested strategies but live trading needs ONE
portfolio; nothing so far decides allocation *across* strategies. This
script closes that gap:

    1. candidates: strategies with a saved backtest, enough history, and a
       PASS from the validation battery (``--include-fail`` relaxes)
    2. correlation: pairwise correlation of monthly return streams
       (computed pairwise, so late-starting strategies don't truncate the
       whole panel — the AIGC lesson applied to strategies)
    3. selection: greedy — take the best Sharpe, then keep adding the next
       best whose |correlation| to everything already selected stays below
       ``--max-corr``, up to ``--max-strategies``
    4. weights: inverse-volatility across the selected set
    5. report: blended Sharpe/vol/drawdown + the selected correlation matrix
       to results/meta_portfolio.json

Research output only — target weights for the MANUAL monthly rebalance.
Never places, modifies, or cancels any order.

Usage:
    python scripts/build_meta_portfolio.py
    python scripts/build_meta_portfolio.py --max-strategies 4 --max-corr 0.6
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from backtesting.results_schema import (  # noqa: E402
    INDEX_FILE,
    VALIDATION_FILE,
    load_portfolio_values,
    strategy_dir,
)

logger = logging.getLogger(__name__)

DEFAULT_OUT = Path("results") / "meta_portfolio.json"
PERIODS_PER_YEAR = 12  # portfolio_history is monthly (rebalance cadence)


def load_candidates(
    results_dir: Path, min_points: int, include_fail: bool
) -> tuple[pd.DataFrame, dict]:
    """
    Load monthly return streams for eligible strategies.

    Returns (returns DataFrame — one column per strategy, NaN outside its
    own history — and a dict of per-strategy metadata).
    """
    index_path = results_dir / INDEX_FILE
    with open(index_path, "r") as f:
        index = json.load(f)

    returns: dict[str, pd.Series] = {}
    meta: dict[str, dict] = {}
    dropped = {"short_history": 0, "validation_fail": 0, "no_validation": 0}

    for key in sorted(index.get("strategies", {})):
        validation_path = strategy_dir(results_dir, key) / VALIDATION_FILE
        verdict = None
        if validation_path.exists():
            try:
                with open(validation_path, "r") as f:
                    verdict = json.load(f).get("overall")
            except Exception:
                pass
        if not include_fail:
            if verdict is None:
                dropped["no_validation"] += 1
                continue
            if verdict != "PASS":
                dropped["validation_fail"] += 1
                continue

        values = load_portfolio_values(results_dir, key)
        if len(values) < min_points:
            dropped["short_history"] += 1
            continue
        r = values.sort_index().pct_change().dropna()
        vol = float(r.std() * np.sqrt(PERIODS_PER_YEAR))
        sharpe = float(r.mean() * PERIODS_PER_YEAR / vol) if vol > 0 else 0.0
        returns[key] = r
        meta[key] = {
            "sharpe": sharpe,
            "volatility": vol,
            "n_points": len(r),
            "start": r.index[0].date().isoformat(),
            "end": r.index[-1].date().isoformat(),
            "validation": verdict,
        }

    logger.info(
        f"{len(returns)} candidates "
        f"(dropped: {dropped['validation_fail']} FAIL, "
        f"{dropped['no_validation']} unvalidated, "
        f"{dropped['short_history']} short history)"
    )
    if not returns:
        return pd.DataFrame(), meta
    return pd.concat(returns, axis=1, sort=True), meta


def greedy_select(
    panel: pd.DataFrame,
    meta: dict,
    max_corr: float,
    max_n: int,
    min_overlap: int,
) -> list[str]:
    """
    Best-Sharpe-first greedy selection under a pairwise correlation cap.

    Correlations are computed pairwise (pandas handles the NaN alignment),
    with a minimum-overlap requirement so a spuriously low correlation from
    a few shared months can't sneak a strategy in.
    """
    corr = panel.corr(min_periods=min_overlap)
    ranked = sorted(meta, key=lambda k: meta[k]["sharpe"], reverse=True)

    selected: list[str] = []
    for key in ranked:
        if len(selected) >= max_n:
            break
        ok = True
        for chosen in selected:
            c = corr.at[key, chosen]
            if pd.isna(c):  # not enough overlap to trust it — refuse
                ok = False
                break
            if abs(c) >= max_corr:
                ok = False
                break
        if ok:
            selected.append(key)
    return selected


def blend_stats(panel: pd.DataFrame, weights: dict[str, float]) -> dict:
    """Stats for the weighted blend on the selected strategies' inner join."""
    joined = panel[list(weights)].dropna()
    blend = sum(joined[k] * w for k, w in weights.items())
    vol = float(blend.std() * np.sqrt(PERIODS_PER_YEAR))
    sharpe = float(blend.mean() * PERIODS_PER_YEAR / vol) if vol > 0 else 0.0
    cumulative = (1 + blend).cumprod()
    running_max = cumulative.cummax()
    max_dd = float(((cumulative - running_max) / running_max).min())
    return {
        "sharpe": sharpe,
        "volatility": vol,
        "max_drawdown": max_dd,
        "total_return": float(cumulative.iloc[-1] - 1),
        "n_points": len(blend),
        "start": joined.index[0].date().isoformat(),
        "end": joined.index[-1].date().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select a decorrelated strategy subset and blend weights.",
    )
    parser.add_argument("--max-strategies", type=int, default=5)
    parser.add_argument(
        "--max-corr",
        type=float,
        default=0.7,
        help="Pairwise |correlation| cap between selected strategies (0.7).",
    )
    parser.add_argument(
        "--min-points",
        type=int,
        default=36,
        help="Minimum monthly observations per candidate (36 = 3 years).",
    )
    parser.add_argument(
        "--min-overlap",
        type=int,
        default=24,
        help="Minimum shared months for a correlation to count (24).",
    )
    parser.add_argument(
        "--include-fail",
        action="store_true",
        help="Consider strategies without a validation PASS as well.",
    )
    parser.add_argument("--results-dir", type=str, default="results")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    results_dir = Path(args.results_dir)

    panel, meta = load_candidates(results_dir, args.min_points, args.include_fail)
    if panel.empty:
        logger.error(
            "No eligible strategies — run the pipeline first, or relax "
            "filters (--include-fail / --min-points)."
        )
        return 1

    selected = greedy_select(
        panel, meta, args.max_corr, args.max_strategies, args.min_overlap
    )
    if not selected:
        logger.error("Selection came up empty — lower --max-corr?")
        return 1

    inv_vol = {k: 1.0 / meta[k]["volatility"] for k in selected}
    total = sum(inv_vol.values())
    weights = {k: v / total for k, v in inv_vol.items()}

    corr_selected = panel[selected].corr(min_periods=args.min_overlap)
    report = {
        "as_of": datetime.now().isoformat(),
        "params": {
            "max_strategies": args.max_strategies,
            "max_corr": args.max_corr,
            "min_points": args.min_points,
            "min_overlap": args.min_overlap,
            "include_fail": args.include_fail,
        },
        "n_candidates": len(meta),
        "selected": [
            {
                "strategy": k,
                "weight": round(weights[k], 4),
                **{f: meta[k][f] for f in ("sharpe", "volatility", "validation")},
            }
            for k in selected
        ],
        "correlation_matrix": {
            k: {j: (None if pd.isna(c) else round(float(c), 3)) for j, c in row.items()}
            for k, row in corr_selected.iterrows()
        },
        "blend": blend_stats(panel, weights),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        f.write("\n")

    logger.info("Selected blend:")
    for entry in report["selected"]:
        logger.info(
            f"  {entry['weight']:>6.1%}  {entry['strategy']}  "
            f"(Sharpe {entry['sharpe']:.2f}, vol {entry['volatility']:.1%})"
        )
    blend = report["blend"]
    logger.info(
        f"Blend: Sharpe {blend['sharpe']:.2f}, vol {blend['volatility']:.1%}, "
        f"maxDD {blend['max_drawdown']:.1%} over {blend['n_points']} months "
        f"-> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
