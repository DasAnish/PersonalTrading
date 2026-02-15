"""
Simple test script to fetch 3HCL price data for the last 2 business days.
"""

import asyncio
import sys
from datetime import datetime
from ib_wrapper import IBClient, Config

# Fix encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("=" * 70)
    print("Testing IB Connection and Fetching 3HCL Data")
    print("=" * 70)

    config = Config()
    print(f"\nConfiguration:")
    print(f"  Host: {config.get('ib_connection.host')}")
    print(f"  Port: {config.get('ib_connection.port')}")
    print(f"  Client ID: {config.get('ib_connection.client_id')}")

    client = IBClient(config)

    try:
        print("\n" + "-" * 70)
        print("Connecting to Interactive Brokers...")
        print("-" * 70)

        await client.connect()
        print("[OK] Successfully connected to IB!")

        if client.is_connected():
            print("[OK] Connection is active")

        print("\n" + "=" * 70)
        print("Fetching 3HCL Price Data (Last 2 Business Days)")
        print("=" * 70)

        print("\nRequesting data for 3HCL...")

        bars = await client.get_historical_bars(
            symbol="3HCL",
            duration="2 D",
            bar_size="1 min",
            what_to_show="TRADES",
            use_rth=True
        )

        if not bars.empty:
            print(f"\n[OK] Successfully retrieved {len(bars)} bars!")
            print(f"\nDate Range: {bars.index[0]} to {bars.index[-1]}")
            print(f"\nPrice Statistics:")
            print(f"  Open (First):  {bars['open'].iloc[0]:.2f}")
            print(f"  Close (Last):  {bars['close'].iloc[-1]:.2f}")
            print(f"  High:          {bars['high'].max():.2f}")
            print(f"  Low:           {bars['low'].min():.2f}")
            print(f"  Avg Volume:    {bars['volume'].mean():,.0f}")

            print(f"\nFirst 10 bars:")
            print(bars.head(10))

            csv_filename = f"3HCL_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            bars.to_csv(csv_filename)
            print(f"\n[OK] Data saved to {csv_filename}")
        else:
            print("\n[WARNING] No data returned")

        remaining = client.get_remaining_requests()
        print(f"\n[OK] Remaining API requests: {remaining}/50")

    except Exception as e:
        print(f"\n[ERROR] {e}")
        print("\nMake sure:")
        print("  1. IB Gateway/TWS is running and logged in")
        print("  2. API connections are enabled in settings")
        print("  3. Port 7497 is correct (or update .env file)")

    finally:
        client.disconnect()
        print("\n[OK] Disconnected from IB")

if __name__ == "__main__":
    asyncio.run(main())
