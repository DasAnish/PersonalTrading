"""
Example demonstrating how to fetch historical market data.

This script shows:
    - Fetching historical bars for a single symbol
    - Fetching data for multiple symbols
    - Downloading extended history beyond single request limits
"""

import asyncio
from datetime import datetime, timedelta
from ib_wrapper import IBClient, Config


async def main():
    config = Config()
    client = IBClient(config)

    try:
        await client.connect()
        print("✓ Connected to IB\n")

        # Example 1: Fetch 1 day of 1-minute bars for AAPL
        print("=" * 60)
        print("Example 1: Fetching 1-minute bars for AAPL")
        print("=" * 60)

        bars = await client.get_historical_bars(
            symbol="AAPL",
            duration="1 D",
            bar_size="1 min",
            what_to_show="TRADES"
        )

        print(f"\nReceived {len(bars)} bars")
        if not bars.empty:
            print(f"\nFirst 5 bars:")
            print(bars.head())
            print(f"\nData range: {bars.index[0]} to {bars.index[-1]}")

        # Example 2: Fetch data for multiple symbols
        print("\n" + "=" * 60)
        print("Example 2: Fetching 5-minute bars for multiple symbols")
        print("=" * 60)

        symbols = ["AAPL", "GOOGL", "MSFT"]
        multi_bars = await client.get_multiple_historical_bars(
            symbols=symbols,
            duration="1 D",
            bar_size="5 mins",
            concurrent=True
        )

        for symbol, data in multi_bars.items():
            print(f"\n{symbol}: {len(data)} bars")
            if not data.empty:
                print(f"  Latest close: ${data['close'].iloc[-1]:.2f}")

        # Example 3: Fetch extended history (beyond single request limit)
        print("\n" + "=" * 60)
        print("Example 3: Downloading extended daily history")
        print("=" * 60)

        start_date = datetime.now() - timedelta(days=90)
        end_date = datetime.now()

        print(f"\nDownloading AAPL daily bars from {start_date.date()} to {end_date.date()}")

        extended_bars = await client.download_extended_history(
            symbol="AAPL",
            start_date=start_date,
            end_date=end_date,
            bar_size="1 day"
        )

        print(f"\nReceived {len(extended_bars)} daily bars")
        if not extended_bars.empty:
            print(f"\nFirst 5 bars:")
            print(extended_bars.head())
            print(f"\nLast 5 bars:")
            print(extended_bars.tail())

        # Show remaining requests
        remaining = client.get_remaining_requests()
        print(f"\n✓ Remaining API requests: {remaining}/50")

    except Exception as e:
        print(f"\n✗ Error: {e}")

    finally:
        client.disconnect()
        print("\n✓ Disconnected from IB")


if __name__ == "__main__":
    asyncio.run(main())
