"""
Example demonstrating real-time portfolio updates and PnL tracking.

This script shows:
    - Subscribing to portfolio updates
    - Subscribing to account-level PnL
    - Subscribing to position-level PnL
    - Real-time event streaming

Note: This requires an active trading session with positions.
      Use Ctrl+C to stop.
"""

import asyncio
from datetime import datetime
from ib_wrapper import IBClient, Config
from ib_wrapper.models import PortfolioUpdate, PnLUpdate, PnLSingleUpdate


async def main():
    config = Config()
    client = IBClient(config)

    # Callback for portfolio updates
    def on_portfolio_update(update: PortfolioUpdate):
        timestamp = update.timestamp.strftime('%H:%M:%S')
        pos = update.position
        print(f"\n[{timestamp}] 📊 Portfolio Update")
        print(f"  Type:           {update.update_type}")
        print(f"  Symbol:         {pos.symbol}")
        print(f"  Position:       {pos.position:,.0f}")
        print(f"  Market Value:   ${pos.market_value:,.2f}")
        print(f"  Unrealized PnL: ${pos.unrealized_pnl:,.2f}")

    # Callback for account PnL updates
    def on_pnl_update(pnl: PnLUpdate):
        timestamp = pnl.timestamp.strftime('%H:%M:%S')
        print(f"\n[{timestamp}] 💰 Account PnL Update")
        print(f"  Account:        {pnl.account}")
        print(f"  Daily PnL:      ${pnl.daily_pnl:,.2f}")
        print(f"  Unrealized PnL: ${pnl.unrealized_pnl:,.2f}")
        print(f"  Realized PnL:   ${pnl.realized_pnl:,.2f}")

    # Callback for position-level PnL updates
    def on_position_pnl_update(pnl: PnLSingleUpdate):
        timestamp = pnl.timestamp.strftime('%H:%M:%S')
        print(f"\n[{timestamp}] 📈 Position PnL Update")
        print(f"  Contract ID:    {pnl.contract_id}")
        print(f"  Position:       {pnl.position:,.0f}")
        print(f"  Daily PnL:      ${pnl.daily_pnl:,.2f}")
        print(f"  Unrealized PnL: ${pnl.unrealized_pnl:,.2f}")
        print(f"  Value:          ${pnl.value:,.2f}")

    try:
        await client.connect()
        print("✓ Connected to IB\n")

        # Subscribe to portfolio updates
        print("=" * 60)
        print("Subscribing to real-time updates...")
        print("=" * 60)

        client.subscribe_portfolio_updates(on_portfolio_update)
        print("✓ Subscribed to portfolio updates")

        # Get account from config or use default
        account = config.get('ib_account')
        if not account:
            # Try to get from first position
            positions = await client.get_positions()
            if positions:
                account = positions[0].account
                print(f"✓ Using account: {account}")

        if account:
            # Subscribe to account PnL
            await client.subscribe_pnl(account, on_pnl_update)
            print(f"✓ Subscribed to account PnL for {account}")

            # Get current positions and subscribe to their PnL
            positions = await client.get_positions()
            if positions:
                print(f"\nSubscribing to PnL for {len(positions)} positions:")
                for pos in positions:
                    await client.subscribe_pnl_single(
                        account,
                        pos.contract_id,
                        on_position_pnl_update
                    )
                    print(f"  ✓ {pos.symbol} (Contract ID: {pos.contract_id})")
            else:
                print("\n⚠ No positions found. Position-level PnL not subscribed.")
        else:
            print("\n⚠ No account found. PnL subscriptions skipped.")
            print("   Set IB_ACCOUNT in .env or ensure you have positions.")

        # Keep running to receive updates
        print("\n" + "=" * 60)
        print("Listening for real-time updates...")
        print("Press Ctrl+C to stop")
        print("=" * 60)

        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\n⚠ Stopping...")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        print("\nCleaning up subscriptions...")
        client.unsubscribe_portfolio_updates()
        await client.unsubscribe_all_pnl()
        print("✓ Unsubscribed from all updates")

        client.disconnect()
        print("✓ Disconnected from IB")


if __name__ == "__main__":
    asyncio.run(main())
