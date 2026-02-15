"""
Portfolio service for Interactive Brokers wrapper.

This module handles portfolio and account operations including
positions, account summary, and real-time PnL updates.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable

from ib_insync import IB

from .models import Position, AccountSummary, PortfolioUpdate, PnLUpdate, PnLSingleUpdate
from .exceptions import PortfolioException
from decimal import Decimal

logger = logging.getLogger(__name__)


class PortfolioService:
    """
    Service for portfolio and account management.

    Handles:
    - Current positions retrieval
    - Account summary and values
    - Real-time portfolio updates
    - Real-time PnL tracking (account and position level)
    """

    def __init__(self, ib: IB):
        """
        Initialize portfolio service.

        Args:
            ib: ib_insync IB instance
        """
        self.ib = ib
        self._portfolio_callback: Optional[Callable] = None
        self._pnl_subscriptions: Dict[str, tuple] = {}
        self._pnl_single_subscriptions: Dict[tuple, tuple] = {}

    async def get_positions(self) -> List[Position]:
        """
        Get current positions.

        Returns:
            List of Position objects

        Examples:
            >>> positions = await service.get_positions()
            >>> for pos in positions:
            ...     print(f"{pos.symbol}: {pos.position} @ {pos.market_price}")
        """
        try:
            logger.debug("Fetching current positions")

            ib_positions = self.ib.positions()

            positions = [
                Position.from_ib_insync(pos)
                for pos in ib_positions
            ]

            logger.info(f"Retrieved {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise PortfolioException(f"Failed to get positions: {e}")

    async def get_account_summary(
        self,
        account: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get account summary information.

        Args:
            account: Account ID (optional, defaults to all accounts)
            tags: List of tags to retrieve (optional, defaults to key metrics)

        Returns:
            Dictionary of account summary values

        Examples:
            >>> summary = await service.get_account_summary()
            >>> print(f"Net Liquidation: ${summary['NetLiquidation']}")
        """
        try:
            default_tags = [
                'NetLiquidation',
                'TotalCashValue',
                'SettledCash',
                'AccruedCash',
                'BuyingPower',
                'EquityWithLoanValue',
                'GrossPositionValue',
                'InitMarginReq',
                'MaintMarginReq'
            ]

            tags_to_request = ','.join(tags) if tags else ','.join(default_tags)
            account_code = account if account else 'All'

            logger.debug(f"Fetching account summary for {account_code}")

            # Request account summary
            summary_items = self.ib.accountSummary(account_code)

            # Convert to dictionary
            result = {}
            for item in summary_items:
                if tags and item.tag not in tags:
                    continue
                try:
                    result[item.tag] = float(item.value) if item.value else 0.0
                except (ValueError, TypeError):
                    result[item.tag] = item.value

            logger.info(f"Retrieved account summary with {len(result)} values")
            return result

        except Exception as e:
            logger.error(f"Failed to get account summary: {e}")
            raise PortfolioException(f"Failed to get account summary: {e}")

    async def get_account_values(
        self,
        account: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get detailed account values.

        Args:
            account: Account ID (optional)

        Returns:
            Dictionary of account values

        Examples:
            >>> values = await service.get_account_values()
            >>> for key, value in values.items():
            ...     print(f"{key}: {value}")
        """
        try:
            logger.debug("Fetching account values")

            account_values = self.ib.accountValues(account)

            result = {}
            for av in account_values:
                key = f"{av.tag}_{av.currency}" if av.currency else av.tag
                try:
                    result[key] = float(av.value) if av.value else 0.0
                except (ValueError, TypeError):
                    result[key] = av.value

            logger.info(f"Retrieved {len(result)} account values")
            return result

        except Exception as e:
            logger.error(f"Failed to get account values: {e}")
            raise PortfolioException(f"Failed to get account values: {e}")

    def subscribe_portfolio_updates(
        self,
        callback: Callable[[PortfolioUpdate], None]
    ):
        """
        Subscribe to real-time portfolio updates.

        Args:
            callback: Function to call on portfolio update

        Examples:
            >>> def on_update(update: PortfolioUpdate):
            ...     print(f"Position updated: {update.position.symbol}")
            >>> service.subscribe_portfolio_updates(on_update)
        """
        def on_portfolio_update(item):
            """Handle portfolio update event from ib_insync."""
            try:
                position = Position(
                    symbol=item.contract.symbol,
                    contract_id=item.contract.conId,
                    position=item.position,
                    market_price=item.marketPrice if item.marketPrice else 0.0,
                    market_value=item.marketValue if item.marketValue else 0.0,
                    average_cost=item.averageCost if item.averageCost else 0.0,
                    unrealized_pnl=item.unrealizedPNL if item.unrealizedPNL else 0.0,
                    realized_pnl=item.realizedPNL if item.realizedPNL else 0.0,
                    account=item.account
                )

                update = PortfolioUpdate(
                    timestamp=datetime.now(),
                    position=position,
                    update_type='modified'
                )

                callback(update)

            except Exception as e:
                logger.error(f"Error processing portfolio update: {e}")

        # Subscribe to ib_insync event
        self.ib.updatePortfolioEvent += on_portfolio_update
        self._portfolio_callback = on_portfolio_update

        logger.info("Subscribed to portfolio updates")

    def unsubscribe_portfolio_updates(self):
        """
        Unsubscribe from portfolio updates.
        """
        if self._portfolio_callback:
            self.ib.updatePortfolioEvent -= self._portfolio_callback
            self._portfolio_callback = None
            logger.info("Unsubscribed from portfolio updates")

    async def subscribe_pnl(
        self,
        account: str,
        callback: Callable[[PnLUpdate], None],
        model_code: str = ""
    ):
        """
        Subscribe to account-level PnL updates.

        Args:
            account: Account ID
            callback: Function to call on PnL update
            model_code: Model code (optional)

        Examples:
            >>> def on_pnl(pnl: PnLUpdate):
            ...     print(f"Daily PnL: ${pnl.daily_pnl:.2f}")
            >>> await service.subscribe_pnl("DU123456", on_pnl)
        """
        def on_pnl_update(pnl):
            """Handle PnL update event."""
            try:
                pnl_update = PnLUpdate(
                    account=account,
                    daily_pnl=pnl.dailyPnL if pnl.dailyPnL else 0.0,
                    unrealized_pnl=pnl.unrealizedPnL if pnl.unrealizedPnL else 0.0,
                    realized_pnl=pnl.realizedPnL if pnl.realizedPnL else 0.0,
                    timestamp=datetime.now()
                )

                callback(pnl_update)

            except Exception as e:
                logger.error(f"Error processing PnL update: {e}")

        # Request PnL subscription
        pnl = self.ib.reqPnL(account, model_code)
        pnl.updateEvent += on_pnl_update

        self._pnl_subscriptions[account] = (pnl, on_pnl_update)
        logger.info(f"Subscribed to PnL updates for account {account}")

    async def subscribe_pnl_single(
        self,
        account: str,
        contract_id: int,
        callback: Callable[[PnLSingleUpdate], None],
        model_code: str = ""
    ):
        """
        Subscribe to position-level PnL updates.

        Args:
            account: Account ID
            contract_id: Contract ID
            callback: Function to call on PnL update
            model_code: Model code (optional)

        Examples:
            >>> def on_position_pnl(pnl: PnLSingleUpdate):
            ...     print(f"Position PnL: ${pnl.unrealized_pnl:.2f}")
            >>> await service.subscribe_pnl_single("DU123456", 12345, on_position_pnl)
        """
        def on_pnl_single_update(pnl_single):
            """Handle position PnL update event."""
            try:
                pnl_update = PnLSingleUpdate(
                    account=account,
                    contract_id=contract_id,
                    position=pnl_single.position if pnl_single.position else 0.0,
                    daily_pnl=pnl_single.dailyPnL if pnl_single.dailyPnL else 0.0,
                    unrealized_pnl=pnl_single.unrealizedPnL if pnl_single.unrealizedPnL else 0.0,
                    realized_pnl=pnl_single.realizedPnL if pnl_single.realizedPnL else 0.0,
                    value=pnl_single.value if pnl_single.value else 0.0,
                    timestamp=datetime.now()
                )

                callback(pnl_update)

            except Exception as e:
                logger.error(f"Error processing position PnL update: {e}")

        # Request PnL single subscription
        pnl_single = self.ib.reqPnLSingle(account, model_code, contract_id)
        pnl_single.updateEvent += on_pnl_single_update

        key = (account, contract_id)
        self._pnl_single_subscriptions[key] = (pnl_single, on_pnl_single_update)

        logger.info(
            f"Subscribed to position PnL updates for "
            f"account {account}, contract {contract_id}"
        )

    def unsubscribe_pnl(self, account: str):
        """
        Unsubscribe from account-level PnL updates.

        Args:
            account: Account ID
        """
        if account in self._pnl_subscriptions:
            pnl, callback = self._pnl_subscriptions[account]
            self.ib.cancelPnL(pnl)
            del self._pnl_subscriptions[account]
            logger.info(f"Unsubscribed from PnL updates for account {account}")

    def unsubscribe_pnl_single(self, account: str, contract_id: int):
        """
        Unsubscribe from position-level PnL updates.

        Args:
            account: Account ID
            contract_id: Contract ID
        """
        key = (account, contract_id)
        if key in self._pnl_single_subscriptions:
            pnl_single, callback = self._pnl_single_subscriptions[key]
            self.ib.cancelPnLSingle(pnl_single)
            del self._pnl_single_subscriptions[key]
            logger.info(
                f"Unsubscribed from position PnL updates for "
                f"account {account}, contract {contract_id}"
            )

    async def unsubscribe_all_pnl(self):
        """
        Unsubscribe from all PnL updates.
        """
        # Cancel account-level PnL
        for account in list(self._pnl_subscriptions.keys()):
            self.unsubscribe_pnl(account)

        # Cancel position-level PnL
        for (account, contract_id) in list(self._pnl_single_subscriptions.keys()):
            self.unsubscribe_pnl_single(account, contract_id)

        logger.info("Unsubscribed from all PnL updates")
