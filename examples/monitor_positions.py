"""
Example demonstrating how to fetch current positions and account data.

This script shows:
    - Getting current positions
    - Getting account summary
    - Getting detailed account values
"""

import asyncio
from ib_wrapper import IBClient, Config


async def main():
    config = Config()
    client = IBClient(config)

    try:
        await client.connect()
        print("✓ Connected to IB\n")

        # Get current positions
        print("=" * 80)
        print("CURRENT POSITIONS")
        print("=" * 80)

        positions = await client.get_positions()

        if not positions:
            print("No positions found")
        else:
            for pos in positions:
                print(f"\n{pos.symbol} (Contract ID: {pos.contract_id})")
                print(f"  Account:        {pos.account}")
                print(f"  Position:       {pos.position:,.0f}")
                print(f"  Market Price:   ${pos.market_price:,.2f}")
                print(f"  Market Value:   ${pos.market_value:,.2f}")
                print(f"  Average Cost:   ${pos.average_cost:,.2f}")
                print(f"  Unrealized PnL: ${pos.unrealized_pnl:,.2f}")
                print(f"  Realized PnL:   ${pos.realized_pnl:,.2f}")

        # Get account summary
        print("\n" + "=" * 80)
        print("ACCOUNT SUMMARY")
        print("=" * 80)

        account_summary = await client.get_account_summary()

        key_metrics = [
            'NetLiquidation',
            'TotalCashValue',
            'BuyingPower',
            'EquityWithLoanValue',
            'GrossPositionValue'
        ]

        for metric in key_metrics:
            if metric in account_summary:
                value = account_summary[metric]
                print(f"{metric:25} ${value:>15,.2f}")

        # Get detailed account values
        print("\n" + "=" * 80)
        print("DETAILED ACCOUNT VALUES")
        print("=" * 80)

        account_values = await client.get_account_values()

        # Group by category (just show first 20)
        print("\nShowing first 20 account values:")
        for i, (key, value) in enumerate(sorted(account_values.items())[:20]):
            if isinstance(value, (int, float)):
                print(f"{key:40} {value:>15,.2f}")
            else:
                print(f"{key:40} {value:>15}")

        print(f"\n✓ Total account values retrieved: {len(account_values)}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        client.disconnect()
        print("\n✓ Disconnected from IB")


if __name__ == "__main__":
    asyncio.run(main())
