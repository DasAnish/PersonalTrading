#!/bin/bash
# Start the HRP Backtest Dashboard

echo "================================"
echo "HRP Backtest Dashboard"
echo "================================"
echo ""
echo "Starting dashboard server..."
echo ""

cd "$(dirname "$0")/.."
python scripts/serve_results.py
