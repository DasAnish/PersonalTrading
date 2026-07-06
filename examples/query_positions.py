"""
Test script to query current positions across all accounts.

This script demonstrates how to:
- Fetch all current positions from IB
- Display position details grouped by account
- Show portfolio summary statistics
- Calculate total P&L across all positions
"""

import asyncio
import sys
from datetime import datetime
from ib_wrapper import IBClient, Config

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')


async def main():
    print("=" * 80)
    print("Interactive Brokers - Position Query")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Load configuration
    config = Config()
    client = IBClient(config)

    try:
        # Connect to IB
        print("Connecting to IB Gateway/TWS...")
        await client.connect()
        print("[OK] Connected successfully!\n")

        # Fetch all positions
        print("=" * 80)
        print("Fetching positions across all accounts...")
        print("=" * 80)

        positions = await client.get_positions()

        if not positions:
            print("\n[INFO] No positions found")
            print("       Either no positions exist or accounts are empty\n")
        else:
            print(f"\n[OK] Found {len(positions)} position(s)\n")

            # Group positions by account
            accounts = {}
            for pos in positions:
                if pos.account not in accounts:
                    accounts[pos.account] = []
                accounts[pos.account].append(pos)

            # Display positions grouped by account
            for account, account_positions in accounts.items():
                print("=" * 80)
                print(f"Account: {account}")
                print("=" * 80)

                # Calculate account totals
                total_market_value = sum(p.market_value for p in account_positions)
                total_unrealized_pnl = sum(p.unrealized_pnl for p in account_positions)
                total_realized_pnl = sum(p.realized_pnl for p in account_positions)

                # Display each position
                for i, pos in enumerate(account_positions, 1):
                    print(f"\nPosition {i}:")
                    print(f"  {'Symbol:':<20} {pos.symbol}")
                    print(f"  {'Contract ID:':<20} {pos.contract_id}")
                    print(f"  {'Quantity:':<20} {pos.position:,.2f}")
                    print(f"  {'Market Price:':<20} {pos.market_price:,.4f}")
                    print(f"  {'Market Value:':<20} {pos.market_value:,.2f}")
                    print(f"  {'Average Cost:':<20} {pos.average_cost:,.4f}")
                    print(f"  {'Unrealized P&L:':<20} {pos.unrealized_pnl:>+,.2f}")
                    print(f"  {'Realized P&L:':<20} {pos.realized_pnl:>+,.2f}")

                    # Calculate percentage gain/loss
                    if pos.average_cost != 0:
                        pnl_percent = (pos.unrealized_pnl / (pos.average_cost * abs(pos.position))) * 100
                        print(f"  {'P&L %:':<20} {pnl_percent:>+.2f}%")

                # Display account summary
                print("\n" + "-" * 80)
                print(f"Account Summary for {account}:")
                print("-" * 80)
                print(f"  Total Positions:      {len(account_positions)}")
                print(f"  Total Market Value:   {total_market_value:>+,.2f}")
                print(f"  Total Unrealized P&L: {total_unrealized_pnl:>+,.2f}")
                print(f"  Total Realized P&L:   {total_realized_pnl:>+,.2f}")
                print()

            # Overall portfolio summary
            if len(accounts) > 1:
                print("=" * 80)
                print("Overall Portfolio Summary (All Accounts)")
                print("=" * 80)

                total_positions = len(positions)
                total_mv = sum(p.market_value for p in positions)
                total_upnl = sum(p.unrealized_pnl for p in positions)
                total_rpnl = sum(p.realized_pnl for p in positions)
                total_pnl = total_upnl + total_rpnl

                print(f"\n  Total Accounts:       {len(accounts)}")
                print(f"  Total Positions:      {total_positions}")
                print(f"  Total Market Value:   {total_mv:>+,.2f}")
                print(f"  Total Unrealized P&L: {total_upnl:>+,.2f}")
                print(f"  Total Realized P&L:   {total_rpnl:>+,.2f}")
                print(f"  Total P&L:            {total_pnl:>+,.2f}")
                print()

        # Fetch account summary
        print("=" * 80)
        print("Account Summary Information")
        print("=" * 80)

        try:
            account_summary = await client.get_account_summary()

            if account_summary:
                print("\nKey Account Metrics:")
                print("-" * 80)

                # Display key metrics
                key_metrics = [
                    ('NetLiquidation', 'Net Liquidation Value'),
                    ('TotalCashValue', 'Total Cash'),
                    ('BuyingPower', 'Buying Power'),
                    ('GrossPositionValue', 'Gross Position Value'),
                    ('EquityWithLoanValue', 'Equity with Loan'),
                ]

                for key, label in key_metrics:
                    if key in account_summary:
                        print(f"  {label:<30} {account_summary[key]:>15,.2f}")

                # Show all other metrics
                other_metrics = {k: v for k, v in account_summary.items()
                               if k not in [m[0] for m in key_metrics]}

                if other_metrics:
                    print("\nOther Metrics:")
                    print("-" * 80)
                    for key, value in sorted(other_metrics.items()):
                        if isinstance(value, (int, float)):
                            print(f"  {key:<30} {value:>15,.2f}")
                        else:
                            print(f"  {key:<30} {value:>15}")
                print()
            else:
                print("\n[INFO] No account summary data available\n")

        except Exception as e:
            print(f"\n[WARNING] Could not fetch account summary: {e}\n")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure IB Gateway/TWS is running and logged in")
        print("  2. Check API settings are enabled")
        print("  3. Verify Read-Only API mode is disabled")
        print("  4. Check port configuration in .env file\n")

        import traceback
        print("\nDetailed error:")
        traceback.print_exc()

    finally:
        # Disconnect
        client.disconnect()
        print("=" * 80)
        print("[OK] Disconnected from IB")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
