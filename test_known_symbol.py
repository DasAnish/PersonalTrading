"""
Test with a known LSE symbol to verify the setup works.
"""

import asyncio
import sys
from ib_wrapper import IBClient, Config

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("Testing with known LSE symbol (HSBA - HSBC Holdings)")
    print("=" * 70)

    config = Config()
    client = IBClient(config)

    try:
        await client.connect()
        print("[OK] Connected!")

        # Test with HSBC (a well-known LSE stock)
        bars = await client.get_historical_bars(
            symbol="HSBA",
            duration="1 D",
            bar_size="5 mins",
            sec_type="STK",
            exchange="LSE",
            currency="GBP"
        )

        if not bars.empty:
            print(f"\n[OK] HSBA data fetched successfully - {len(bars)} bars")
            print(f"Latest close: {bars['close'].iloc[-1]:.2f} GBP")
            print("\n[SUCCESS] Your IB wrapper is working correctly!")
            print("The issue is just finding the correct symbol for 3HCL.LN")
        else:
            print("[WARNING] Connected but no data (might be read-only mode)")

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
