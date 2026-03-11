"""
Predefined market strategies that define asset universes.

Market strategies define which instruments are traded and their specifications
(currency, exchange, security type). They cannot be run directly but must be
wrapped by an allocation strategy (HRP, EqualWeight, etc.).

Examples:
    # UK ETF market
    market = UKETFsMarket()
    hrp = HRPStrategy(underlying=market)
    results = await hrp.run(engine, start_date, end_date)

    # Custom market
    custom = CustomMarket(
        symbols=['AAPL', 'MSFT', 'GOOGL'],
        currency='USD'
    )
    ew = EqualWeightStrategy(underlying=custom)
    results = await ew.run(engine, start_date, end_date)
"""

from typing import List, Optional
from strategies.base import MarketStrategy
from strategies.models import Instrument, MarketDefinition


class UKETFsMarket(MarketStrategy):
    """UK ETF universe: VUSA, SSLN, SGLN, IWRD (GBP)."""

    def __init__(self):
        """Initialize UK ETF market definition."""
        instruments = [
            Instrument("VUSA", sec_type="STK", exchange="SMART", currency="GBP"),
            Instrument("SSLN", sec_type="STK", exchange="SMART", currency="GBP"),
            Instrument("SGLN", sec_type="STK", exchange="SMART", currency="GBP"),
            Instrument("IWRD", sec_type="STK", exchange="SMART", currency="GBP"),
        ]
        market_def = MarketDefinition(instruments, name="UK ETFs")
        super().__init__(market_def, name="UK ETFs Market")


class USEquitiesMarket(MarketStrategy):
    """US equities market with configurable symbols."""

    def __init__(
        self,
        symbols: List[str] = None,
        exchange: str = "SMART",
        currency: str = "USD",
    ):
        """
        Initialize US equities market.

        Args:
            symbols: List of stock symbols. Defaults to tech stocks: AAPL, MSFT, GOOGL, AMZN
            exchange: Exchange for orders. Default: SMART
            currency: Quote currency. Default: USD
        """
        if symbols is None:
            symbols = ["AAPL", "MSFT", "GOOGL", "AMZN"]

        instruments = [
            Instrument(symbol, sec_type="STK", exchange=exchange, currency=currency)
            for symbol in symbols
        ]
        market_def = MarketDefinition(instruments, name="US Equities")
        super().__init__(market_def, name="US Equities Market")


class CustomMarket(MarketStrategy):
    """Custom market with user-defined instruments."""

    def __init__(
        self,
        symbols: List[str] = None,
        instruments: List[Instrument] = None,
        name: str = "Custom Market",
    ):
        """
        Initialize custom market.

        Args:
            symbols: List of stock symbols (assumes STK, SMART, USD)
            instruments: Explicit list of Instrument objects
            name: Market name for display

        Example:
            # Simple symbols
            market = CustomMarket(symbols=['VUSA', 'VGOV', 'VBTA'])

            # Explicit instruments with different specs
            instruments = [
                Instrument('AAPL', currency='USD'),
                Instrument('0001.HK', currency='HKD', exchange='HKEX'),
            ]
            market = CustomMarket(instruments=instruments)
        """
        if instruments is None:
            if symbols is None:
                raise ValueError("Either 'symbols' or 'instruments' must be provided")
            instruments = [
                Instrument(symbol, sec_type="STK", exchange="SMART", currency="USD")
                for symbol in symbols
            ]

        market_def = MarketDefinition(instruments, name=name)
        super().__init__(market_def, name=f"{name} Market")


class EuropeanEquitiesMarket(MarketStrategy):
    """European equities market with configurable symbols and currency."""

    def __init__(
        self,
        symbols: List[str] = None,
        exchange: str = "SMART",
        currency: str = "EUR",
    ):
        """
        Initialize European equities market.

        Args:
            symbols: List of stock symbols. Defaults to ASML, SAP, Unilever, Nestle
            exchange: Exchange for orders. Default: SMART
            currency: Quote currency. Default: EUR
        """
        if symbols is None:
            symbols = ["ASML", "SAP", "UNA", "NSRGY"]

        instruments = [
            Instrument(symbol, sec_type="STK", exchange=exchange, currency=currency)
            for symbol in symbols
        ]
        market_def = MarketDefinition(instruments, name="European Equities")
        super().__init__(market_def, name="European Equities Market")


class BondsMarket(MarketStrategy):
    """Fixed income market with bond ETFs."""

    def __init__(self):
        """Initialize bonds market (US Treasury and Corporate)."""
        instruments = [
            Instrument("SHY", sec_type="STK", exchange="SMART", currency="USD"),  # Short-term Treasuries
            Instrument("TLT", sec_type="STK", exchange="SMART", currency="USD"),  # Long-term Treasuries
            Instrument("LQD", sec_type="STK", exchange="SMART", currency="USD"),  # Investment Grade Corp
            Instrument("HYG", sec_type="STK", exchange="SMART", currency="USD"),  # High Yield Corp
        ]
        market_def = MarketDefinition(instruments, name="Bonds")
        super().__init__(market_def, name="Bonds Market")


class CommunitiesMarket(MarketStrategy):
    """Commodities market with ETFs."""

    def __init__(self):
        """Initialize commodities market (oil, gold, agriculture)."""
        instruments = [
            Instrument("USO", sec_type="STK", exchange="SMART", currency="USD"),  # Oil
            Instrument("GLD", sec_type="STK", exchange="SMART", currency="USD"),  # Gold
            Instrument("DBC", sec_type="STK", exchange="SMART", currency="USD"),  # Broad commodities
            Instrument("CANE", sec_type="STK", exchange="SMART", currency="USD"),  # Agriculture
        ]
        market_def = MarketDefinition(instruments, name="Commodities")
        super().__init__(market_def, name="Commodities Market")
