"""
Basic connection example demonstrating how to connect to IB Gateway/TWS.

Prerequisites:
    - IB Gateway or TWS running
    - API connections enabled
    - Correct port configured in .env or config
"""

import asyncio
from ib_wrapper import IBClient, Config


async def main():
    # Load configuration
    config = Config()

    # Create client
    client = IBClient(config)

    try:
        # Connect to IB
        print("Connecting to Interactive Brokers...")
        await client.connect()
        print("✓ Connected to IB successfully!")

        # Check connection status
        if client.is_connected():
            print("✓ Connection is active")

        # Keep connection alive for a few seconds
        print("\nHolding connection for 5 seconds...")
        await asyncio.sleep(5)

    except Exception as e:
        print(f"✗ Error: {e}")

    finally:
        # Disconnect
        client.disconnect()
        print("\n✓ Disconnected from IB")


if __name__ == "__main__":
    asyncio.run(main())
