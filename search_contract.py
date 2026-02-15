"""
Interactive contract search to find the correct IB symbol.
"""

import asyncio
import sys
from ib_wrapper import IBClient, Config
from ib_insync import Stock

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("=" * 70)
    print("Interactive Brokers Contract Search")
    print("=" * 70)

    config = Config()
    client = IBClient(config)

    try:
        await client.connect()
        print("\n[OK] Connected to IB!")

        # Search patterns to try
        search_terms = [
            "3HCL",
            "HCL",
            "3i",  # Could it be 3i Group PLC?
        ]

        for term in search_terms:
            print(f"\n{'='*70}")
            print(f"Searching for: '{term}'")
            print("=" * 70)

            try:
                # Try to search for matching contracts
                # Using IB's contract search
                stock = Stock(term, 'SMART', 'GBP')
                contracts = await client.connection.ib.qualifyContractsAsync(stock)
                
                if contracts:
                    print(f"\n[OK] Found {len(contracts)} contract(s):")
                    for i, contract in enumerate(contracts, 1):
                        print(f"\n  Contract {i}:")
                        print(f"    Symbol:    {contract.symbol}")
                        print(f"    Name:      {contract.localSymbol}")
                        print(f"    Exchange:  {contract.exchange}")
                        print(f"    Currency:  {contract.currency}")
                        print(f"    ConId:     {contract.conId}")
                        print(f"    Sec Type:  {contract.secType}")
                else:
                    print(f"[FAIL] No contracts found for '{term}'")

            except Exception as e:
                print(f"[ERROR] {e}")

        print("\n" + "=" * 70)
        print("\nCan you provide more details about the security:")
        print("  - Full company name?")
        print("  - ISIN or SEDOL code?") 
        print("  - Is it definitely a stock (not ETF/fund)?")
        print("  - Which exchange exactly (LSE, LSE IOB, etc.)?")
        print("=" * 70)

    except Exception as e:
        print(f"\n[ERROR] {e}")

    finally:
        client.disconnect()
        print("\n[OK] Disconnected")

if __name__ == "__main__":
    asyncio.run(main())
