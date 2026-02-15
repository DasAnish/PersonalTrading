"""
Test script to fetch 3HCL price data for the last 2 business days.
"""

import asyncio
from datetime import datetime
from ib_wrapper import IBClient, Config


async def main():
    print("=" * 70)
    print("Testing IB Connection and Fetching 3HCL Data")
    print("=" * 70)

    # Load configuration
    config = Config()
    print(f"\nConfiguration:")
    print(f"  Host: {config.get('ib_connection.host')}")
    print(f"  Port: {config.get('ib_connection.port')}")
    print(f"  Client ID: {config.get('ib_connection.client_id')}")

    # Create client
    client = IBClient(config)

    try:
        # Connect to IB
        print("\n" + "-" * 70)
        print("Connecting to Interactive Brokers...")
        print("-" * 70)

        await client.connect()
        print("✓ Successfully connected to IB!")

        # Check connection status
        if client.is_connected():
            print("✓ Connection is active and healthy")

        # Fetch 2 days of 1-minute bars for 3HCL
        print("\n" + "=" * 70)
        print("Fetching 3HCL Price Data (Last 2 Business Days)")
        print("=" * 70)

        print("\nRequesting data...")
        print("  Symbol: 3HCL")
        print("  Duration: 2 D (2 business days)")
        print("  Bar Size: 1 min")
        print("  Data Type: TRADES")

        bars = await client.get_historical_bars(
            symbol="3HCL",
            duration="2 D",
            bar_size="1 min",
            what_to_show="TRADES",
            use_rth=True  # Regular trading hours only
        )

        if bars.empty:
            print("\n⚠ No data returned for 3HCL")
            print("\nPossible reasons:")
            print("  1. Invalid symbol (check if '3HCL' is correct)")
            print("  2. No market data subscription for this symbol")
            print("  3. Symbol not traded in the last 2 days")
            print("  4. Need to specify exchange or security type")

            # Try with NSE (National Stock Exchange) if it's an Indian stock
            print("\n" + "-" * 70)
            print("Trying with NSE exchange...")
            print("-" * 70)

            bars = await client.get_historical_bars(
                symbol="3HCL",
                duration="2 D",
                bar_size="1 min",
                what_to_show="TRADES",
                exchange="NSE",
                currency="INR"
            )

        if not bars.empty:
            print(f"\n✓ Successfully retrieved {len(bars)} bars!")

            # Display summary statistics
            print("\n" + "-" * 70)
            print("Data Summary")
            print("-" * 70)
            print(f"Total Bars: {len(bars)}")
            print(f"Date Range: {bars.index[0]} to {bars.index[-1]}")
            print(f"\nPrice Statistics:")
            print(f"  Open (First):  ${bars['open'].iloc[0]:.2f}")
            print(f"  Close (Last):  ${bars['close'].iloc[-1]:.2f}")
            print(f"  High:          ${bars['high'].max():.2f}")
            print(f"  Low:           ${bars['low'].min():.2f}")
            print(f"  Avg Volume:    {bars['volume'].mean():,.0f}")
            print(f"  Total Volume:  {bars['volume'].sum():,.0f}")

            # Display first 10 bars
            print("\n" + "-" * 70)
            print("First 10 Bars")
            print("-" * 70)
            print(bars.head(10).to_string())

            # Display last 10 bars
            print("\n" + "-" * 70)
            print("Last 10 Bars")
            print("-" * 70)
            print(bars.tail(10).to_string())

            # Price change analysis
            price_change = bars['close'].iloc[-1] - bars['open'].iloc[0]
            price_change_pct = (price_change / bars['open'].iloc[0]) * 100

            print("\n" + "-" * 70)
            print("Price Change Analysis (2 Days)")
            print("-" * 70)
            print(f"Opening Price:   ${bars['open'].iloc[0]:.2f}")
            print(f"Closing Price:   ${bars['close'].iloc[-1]:.2f}")
            print(f"Change:          ${price_change:+.2f}")
            print(f"Change %:        {price_change_pct:+.2f}%")

            # Save to CSV
            csv_filename = f"3HCL_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            bars.to_csv(csv_filename)
            print(f"\n✓ Data saved to {csv_filename}")

        # Check remaining API requests
        remaining = client.get_remaining_requests()
        print(f"\n✓ Remaining API requests: {remaining}/50")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()

        print("\n" + "=" * 70)
        print("Troubleshooting Tips:")
        print("=" * 70)
        print("1. Make sure IB Gateway or TWS is running and logged in")
        print("2. Check that API connections are enabled:")
        print("   Settings → API → Settings → Enable ActiveX and Socket Clients")
        print("3. Verify the port number:")
        print("   - 7497 for TWS paper trading")
        print("   - 7496 for TWS live trading")
        print("   - 4002 for IB Gateway paper trading")
        print("   - 4001 for IB Gateway live trading")
        print("4. Make sure 127.0.0.1 is in the trusted IPs list")
        print("5. Check if you have market data subscription for 3HCL")

    finally:
        # Disconnect
        print("\n" + "-" * 70)
        client.disconnect()
        print("✓ Disconnected from IB")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
