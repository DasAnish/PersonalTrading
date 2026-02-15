"""
Test script to fetch 3HCL.LN (London Stock Exchange) price data.
"""

import asyncio
import sys
from datetime import datetime
from ib_wrapper import IBClient, Config

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("=" * 70)
    print("Testing 3HCL.LN (London Stock Exchange)")
    print("=" * 70)

    config = Config()
    client = IBClient(config)

    try:
        await client.connect()
        print("\n[OK] Connected to IB!")

        # Try different exchange formats for LSE
        test_configs = [
            ("3HCL", "STK", "LSE", "GBP"),      # London Stock Exchange
            ("3HCL", "STK", "LSEETF", "GBP"),   # LSE ETF
            ("3HCL", "STK", "SMART", "GBP"),    # Smart routing with GBP
        ]

        success = False
        for symbol, sec_type, exchange, currency in test_configs:
            print(f"\n{'='*70}")
            print(f"Trying: {symbol} on {exchange} in {currency}")
            print("=" * 70)
            
            try:
                bars = await client.get_historical_bars(
                    symbol=symbol,
                    duration="2 D",
                    bar_size="1 min",
                    what_to_show="TRADES",
                    use_rth=True,
                    sec_type=sec_type,
                    exchange=exchange,
                    currency=currency
                )

                if not bars.empty:
                    print(f"\n[OK] Successfully retrieved {len(bars)} bars!")
                    print(f"\nDate Range: {bars.index[0]} to {bars.index[-1]}")
                    print(f"\nPrice Statistics (in {currency}):")
                    print(f"  Open (First):  {bars['open'].iloc[0]:.4f}")
                    print(f"  Close (Last):  {bars['close'].iloc[-1]:.4f}")
                    print(f"  High:          {bars['high'].max():.4f}")
                    print(f"  Low:           {bars['low'].min():.4f}")
                    print(f"  Avg Volume:    {bars['volume'].mean():,.0f}")

                    print(f"\nFirst 10 bars:")
                    print(bars.head(10))

                    print(f"\nLast 10 bars:")
                    print(bars.tail(10))

                    # Price change
                    price_change = bars['close'].iloc[-1] - bars['open'].iloc[0]
                    price_change_pct = (price_change / bars['open'].iloc[0]) * 100

                    print(f"\nPrice Change (2 Days):")
                    print(f"  Opening:  {bars['open'].iloc[0]:.4f} {currency}")
                    print(f"  Closing:  {bars['close'].iloc[-1]:.4f} {currency}")
                    print(f"  Change:   {price_change:+.4f} {currency}")
                    print(f"  Change %: {price_change_pct:+.2f}%")

                    # Save to CSV
                    csv_filename = f"3HCL_LN_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    bars.to_csv(csv_filename)
                    print(f"\n[OK] Data saved to {csv_filename}")

                    success = True
                    break
                else:
                    print(f"[WARNING] No data returned for {symbol} on {exchange}")

            except Exception as e:
                print(f"[ERROR] {e}")

        if not success:
            print("\n" + "=" * 70)
            print("No data found. Please check:")
            print("  1. Read-Only API mode is disabled in IB Gateway")
            print("  2. You have market data subscription for LSE")
            print("  3. The symbol '3HCL' is correct for London exchange")
            print("=" * 70)

        remaining = client.get_remaining_requests()
        print(f"\n[OK] Remaining API requests: {remaining}/50")

    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        client.disconnect()
        print("\n[OK] Disconnected from IB")

if __name__ == "__main__":
    asyncio.run(main())
