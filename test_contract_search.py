"""
Test script to search for contract and fetch data.
"""

import asyncio
import sys
from ib_wrapper import IBClient, Config
from ib_wrapper.utils import create_contract

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    config = Config()
    client = IBClient(config)

    try:
        await client.connect()
        print("[OK] Connected to IB!\n")

        # Try different variations of the symbol
        test_configs = [
            ("3HCL", "STK", "NSE", "INR"),     # Indian stock on NSE
            ("3HCL", "STK", "SMART", "INR"),   # Smart routing with INR
            ("HCL", "STK", "NSE", "INR"),      # Without the 3
            ("HCLTECH", "STK", "NSE", "INR"),  # Full name
        ]

        for symbol, sec_type, exchange, currency in test_configs:
            print(f"\nTrying: {symbol} | {sec_type} | {exchange} | {currency}")
            print("-" * 60)
            
            try:
                contract = create_contract(
                    symbol=symbol,
                    sec_type=sec_type,
                    exchange=exchange,
                    currency=currency
                )
                
                # Try to qualify the contract
                qualified = await client.connection.ib.qualifyContractsAsync(contract)
                
                if qualified:
                    print(f"[OK] Found contract: {qualified[0]}")
                    print(f"     Full details: {qualified[0]}")
                    
                    # Try to fetch some data
                    print("\n     Fetching 1 day of data...")
                    bars = await client.get_historical_bars(
                        symbol=symbol,
                        duration="1 D",
                        bar_size="1 min",
                        exchange=exchange,
                        currency=currency
                    )
                    
                    if not bars.empty:
                        print(f"     [OK] Got {len(bars)} bars!")
                        print(f"     Latest close: {bars['close'].iloc[-1]:.2f} {currency}")
                        break
                    else:
                        print("     [WARNING] Contract found but no data")
                else:
                    print(f"[FAIL] Contract not found")
                    
            except Exception as e:
                print(f"[ERROR] {e}")

        print("\n" + "=" * 60)
        print("If none worked, please provide:")
        print("  1. The full company name")
        print("  2. The exchange (e.g., NSE, NYSE, NASDAQ)")
        print("  3. The country/currency")
        print("=" * 60)

    except Exception as e:
        print(f"[ERROR] {e}")

    finally:
        client.disconnect()
        print("\n[OK] Disconnected")

if __name__ == "__main__":
    asyncio.run(main())
