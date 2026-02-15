"""
Data models for Interactive Brokers wrapper.

This module defines type-safe dataclasses for all IB data structures,
including positions, account information, historical bars, and real-time updates.
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any, Dict


@dataclass
class Position:
    """Represents a trading position."""

    symbol: str
    contract_id: int
    position: float
    market_price: float
    market_value: float
    average_cost: float
    unrealized_pnl: float
    realized_pnl: float
    account: str

    @classmethod
    def from_ib_insync(cls, ib_position: Any) -> 'Position':
        """
        Create Position from ib_insync Position object.

        Args:
            ib_position: ib_insync Position object

        Returns:
            Position instance
        """
        return cls(
            symbol=ib_position.contract.symbol,
            contract_id=ib_position.contract.conId,
            position=ib_position.position,
            market_price=ib_position.marketPrice if ib_position.marketPrice else 0.0,
            market_value=ib_position.marketValue if ib_position.marketValue else 0.0,
            average_cost=ib_position.averageCost if ib_position.averageCost else 0.0,
            unrealized_pnl=ib_position.unrealizedPNL if ib_position.unrealizedPNL else 0.0,
            realized_pnl=ib_position.realizedPNL if ib_position.realizedPNL else 0.0,
            account=ib_position.account
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class AccountSummary:
    """Account summary information."""

    account_id: str
    net_liquidation: Decimal
    total_cash_value: Decimal
    settled_cash: Decimal
    excess_liquidity: Decimal
    buying_power: Decimal
    equity_with_loan_value: Decimal
    gross_position_value: Optional[Decimal] = None
    init_margin_req: Optional[Decimal] = None
    maint_margin_req: Optional[Decimal] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert Decimal to float for JSON compatibility
        return {k: float(v) if isinstance(v, Decimal) else v for k, v in data.items()}


@dataclass
class HistoricalBar:
    """Single historical bar data (OHLCV)."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    average: float
    bar_count: int

    @classmethod
    def from_ib_insync(cls, ib_bar: Any) -> 'HistoricalBar':
        """
        Create HistoricalBar from ib_insync BarData object.

        Args:
            ib_bar: ib_insync BarData object

        Returns:
            HistoricalBar instance
        """
        return cls(
            timestamp=ib_bar.date,
            open=ib_bar.open,
            high=ib_bar.high,
            low=ib_bar.low,
            close=ib_bar.close,
            volume=ib_bar.volume,
            average=ib_bar.average if ib_bar.average else 0.0,
            bar_count=ib_bar.barCount if ib_bar.barCount else 0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class PortfolioUpdate:
    """Real-time portfolio update event."""

    timestamp: datetime
    position: Position
    update_type: str  # 'new', 'modified', 'deleted'

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'position': self.position.to_dict(),
            'update_type': self.update_type
        }


@dataclass
class ConnectionConfig:
    """Connection configuration settings."""

    host: str = '127.0.0.1'
    port: int = 7497  # 7497 for TWS paper, 4001 for IB Gateway paper
    client_id: int = 1
    timeout: int = 10
    readonly: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class PnLUpdate:
    """Account-level PnL update."""

    account: str
    daily_pnl: float
    unrealized_pnl: float
    realized_pnl: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class PnLSingleUpdate:
    """Position-level PnL update."""

    account: str
    contract_id: int
    position: float
    daily_pnl: float
    unrealized_pnl: float
    realized_pnl: float
    value: float
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data
