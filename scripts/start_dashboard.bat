@echo off
REM Start the HRP Backtest Dashboard

echo ================================
echo HRP Backtest Dashboard
echo ================================
echo.
echo Starting dashboard server...
echo.

cd /d "%~dp0.."
python scripts/serve_results.py

pause
