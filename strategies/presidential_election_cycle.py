"""
Presidential Election Cycle Seasonality strategy.

Pure calendar rotation keyed off months elapsed since the most recent US
presidential inauguration (Jan 20, every 4 years). Tilts the equity sleeve
up in the historically strong second/third year of a presidential term and
toward defensives in the historically weak first year, holding a neutral
equal-weight baseline across the full universe in the fourth (election)
year.

Based on Herbst & Slinkman (1984) "Political-Economic Cycles in the U.S.
Stock Market" (Financial Analysts Journal 40(2), 38-44), which documents
4-year and 2-year political-economic cycles in US equity prices from
1926-1977, later popularized as the "Presidential Election Cycle" pattern
(Stock Trader's Almanac). This is a genuinely disputed, low-power effect:
only ~12-15 non-overlapping 4-year cycles exist in the historical record,
and critics attribute the pattern to business-cycle/monetary-policy
confounds rather than a distinct seasonal effect. The signal itself is a
deterministic calendar rule and requires no price data; price data is only
used to construct the tilted weight vector across the actually-available
assets.

References:
- Herbst & Slinkman (1984): "Political-Economic Cycles in the U.S. Stock
  Market", Financial Analysts Journal 40(2), 38-44
- research/ideas/presidential-election-cycle.md (pre-registered hypothesis)

Example:
    assets = [
        AssetStrategy('VUSA'), AssetStrategy('EQQQ'), AssetStrategy('IWRD'),
        AssetStrategy('IMEU'), AssetStrategy('IIND'), AssetStrategy('AIGC'),
        AssetStrategy('VUTY'), AssetStrategy('SGLN'), AssetStrategy('BRNT'),
        AssetStrategy('COMM'), AssetStrategy('CRUD'), AssetStrategy('SSLN'),
        AssetStrategy('WCOA'),
    ]
    strategy = PresidentialCycleSeasonalityStrategy(
        underlying=assets, tilt_magnitude_pp=15
    )
    weights = strategy.calculate_weights(context)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Set

import pandas as pd

from strategies.core import AllocationStrategy, Strategy, StrategyContext

logger = logging.getLogger(__name__)

# Equity sleeve (tilted up in cycle years 2-3, down in cycle year 1).
EQUITY_SLEEVE = {'VUSA', 'EQQQ', 'IWRD', 'IMEU', 'IIND', 'AIGC'}

# Defensive sleeve (tilted up in cycle year 1, down in cycle years 2-3).
DEFENSIVE_SLEEVE = {'VUTY', 'SGLN'}

# US presidential inaugurations occur every 4 years on Jan 20. 2025 is used
# as the anchor year, but the residue class (year % 4 == 1) also covers all
# real historical inaugurations (2021, 2017, 2013, ...), so this correctly
# classifies backtest dates before 2025 as well.
INAUGURATION_ANCHOR_YEAR = 2025
INAUGURATION_MONTH = 1
INAUGURATION_DAY = 20

# 4-year term = 48 months, split into 4 twelve-month "cycle years".
MONTHS_PER_CYCLE_YEAR = 12


def _most_recent_inauguration(current_date: datetime) -> datetime:
    """Return the most recent US presidential inauguration on/before current_date.

    Inaugurations recur every 4 years on Jan 20 (years satisfying
    ``year % 4 == INAUGURATION_ANCHOR_YEAR % 4``, e.g. 2025, 2029, ... and
    equivalently 2021, 2017, ... going backward for historical backtests).
    """
    residue = INAUGURATION_ANCHOR_YEAR % 4
    year = current_date.year
    while year % 4 != residue:
        year -= 1

    candidate = datetime(year, INAUGURATION_MONTH, INAUGURATION_DAY)
    if candidate > current_date:
        candidate = datetime(year - 4, INAUGURATION_MONTH, INAUGURATION_DAY)
    return candidate


def _cycle_year(current_date: datetime) -> int:
    """Classify current_date into presidential cycle year 1-4.

    Year 1 = first 12 months post-inauguration (historically weakest per
    the popularized pattern), years 2-3 = strongest, year 4 = election year
    (mixed findings in the source literature, treated as neutral here).
    """
    inauguration = _most_recent_inauguration(current_date)

    months_elapsed = (
        (current_date.year - inauguration.year) * 12
        + (current_date.month - inauguration.month)
    )
    if current_date.day < inauguration.day:
        months_elapsed -= 1
    months_elapsed = max(months_elapsed, 0)

    cycle_year = months_elapsed // MONTHS_PER_CYCLE_YEAR + 1
    return min(cycle_year, 4)


class PresidentialCycleSeasonalityStrategy(AllocationStrategy):
    """
    Presidential Election Cycle Seasonality allocation strategy.

    Starts from an equal-weight baseline across the full available universe.
    Each month, classifies the current date into a 4-year presidential-cycle
    year and applies a directional tilt:
      - Cycle year 1 (weakest, per Herbst & Slinkman / Stock Trader's
        Almanac): tilt `tilt_magnitude_pp` from the equity sleeve into the
        defensive sleeve (VUTY, SGLN).
      - Cycle years 2-3 (strongest): tilt `tilt_magnitude_pp` from the
        defensive sleeve into the equity sleeve (VUSA, EQQQ, IWRD, IMEU,
        IIND, AIGC).
      - Cycle year 4 (election year, mixed findings): no tilt, neutral
        equal-weight baseline.

    Only uses assets actually present in the rebalance universe. If either
    sleeve involved in a given cycle year's tilt is unavailable, the tilt is
    skipped and the neutral equal-weight baseline is held instead.

    Attributes:
        tilt_magnitude_pp: Percentage points shifted from the neutral
            baseline toward equities (years 2-3) or defensives (year 1).
    """

    def __init__(
        self,
        underlying: List[Strategy],
        tilt_magnitude_pp: float = 15.0,
        name: str = None,
    ):
        """
        Initialize Presidential Election Cycle Seasonality strategy.

        Args:
            underlying: List of underlying strategies (assets), ideally the
                full available universe (the cycle-year-4 neutral baseline
                equal-weights all of it).
            tilt_magnitude_pp: Percentage points to tilt toward equities
                (cycle years 2-3) or defensives (cycle year 1), e.g. 15 = 15pp.
            name: Display name
        """
        super().__init__(
            underlying=underlying,
            name=name or f"Presidential Election Cycle Seasonality ({tilt_magnitude_pp:.0f}pp)",
        )
        self.tilt_magnitude_pp = tilt_magnitude_pp
        self.tilt_magnitude = tilt_magnitude_pp / 100.0

    def calculate_weights(self, context: StrategyContext) -> pd.Series:
        """
        Calculate presidential-cycle-tilted weights based on the current date.

        Args:
            context: StrategyContext with prices, current_date, and metadata

        Returns:
            pd.Series with index=asset names, values=weights.
            Weights sum to 1.0 (long-only).

        Logic:
            - Start with equal weight across all available assets
            - Classify current_date into cycle year 1-4
            - Year 1: tilt tilt_magnitude_pp from equity sleeve to defensive sleeve
            - Years 2-3: tilt tilt_magnitude_pp from defensive sleeve to equity sleeve
            - Year 4: no tilt (neutral baseline)
            - Clip negative weights to 0 and renormalize to sum to 1.0
        """
        available_symbols = set(context.prices.columns)
        symbol_to_name = self._build_name_map()
        strategy_names = [s.name for s in self.underlying]

        num_assets = len(strategy_names)
        if num_assets == 0:
            return pd.Series(dtype=float)

        # Neutral baseline: equal weight across the full available universe
        weights = pd.Series(1.0 / num_assets, index=strategy_names)

        cycle_year = _cycle_year(context.current_date)

        equity_names = self._sleeve_names(
            EQUITY_SLEEVE, available_symbols, symbol_to_name, strategy_names
        )
        defensive_names = self._sleeve_names(
            DEFENSIVE_SLEEVE, available_symbols, symbol_to_name, strategy_names
        )

        logger.debug(
            f"PresidentialCycle: date={context.current_date}, cycle_year={cycle_year}, "
            f"equity_sleeve={equity_names}, defensive_sleeve={defensive_names}"
        )

        if cycle_year == 1:
            # Weak year: tilt from equities into defensives
            weights = self._apply_tilt(weights, equity_names, defensive_names)
        elif cycle_year in (2, 3):
            # Strong years: tilt from defensives into equities
            weights = self._apply_tilt(weights, defensive_names, equity_names)
        # cycle_year == 4 (election year): hold neutral baseline, no tilt

        # Clip negative weights (can arise if a tilt exceeds a sleeve's base
        # weight) and renormalize to sum to 1.0
        weights = weights.clip(lower=0.0)
        weights_sum = weights.sum()
        if weights_sum > 0:
            weights = weights / weights_sum
        else:
            weights = pd.Series(1.0 / num_assets, index=strategy_names)

        logger.debug(
            f"PresidentialCycle weights: {dict(weights[weights > 0].round(4))}"
        )

        return weights

    def get_strategy_lookback(self) -> int:
        """
        PresidentialCycleSeasonality requires only current prices (the
        signal is a deterministic calendar rule, not derived from price
        history).

        Returns:
            0 (no lookback needed)
        """
        return 0

    def _apply_tilt(
        self, weights: pd.Series, from_names: Set[str], to_names: Set[str]
    ) -> pd.Series:
        """
        Shift tilt_magnitude pro-rata from one sleeve's strategies to another's.

        Args:
            weights: Current weights (mutated copy is returned)
            from_names: Strategy names to reduce weight from
            to_names: Strategy names to add weight to

        Returns:
            New pd.Series with the tilt applied. If either sleeve is empty
            (not present in the rebalance universe), returns weights
            unchanged (neutral baseline held).
        """
        if not from_names or not to_names:
            logger.debug(
                "PresidentialCycle: tilt sleeve unavailable, holding neutral baseline"
            )
            return weights

        weights = weights.copy()
        reduction_per_asset = self.tilt_magnitude / len(from_names)
        addition_per_asset = self.tilt_magnitude / len(to_names)

        for name in from_names:
            weights[name] -= reduction_per_asset
        for name in to_names:
            weights[name] += addition_per_asset

        return weights

    def _sleeve_names(
        self,
        sleeve_symbols: set,
        available_symbols: set,
        symbol_to_name: dict,
        strategy_names: list,
    ) -> Set[str]:
        """Resolve a sleeve's symbols to strategy names present in this universe."""
        names = {
            symbol_to_name.get(sym, sym)
            for sym in sleeve_symbols & available_symbols
        }
        return names & set(strategy_names)

    def _build_name_map(self) -> dict:
        """Build mapping from symbol to strategy name."""
        symbol_to_name = {}
        for strategy in self.underlying:
            for symbol in strategy.get_symbols():
                symbol_to_name[symbol] = strategy.name
        return symbol_to_name
