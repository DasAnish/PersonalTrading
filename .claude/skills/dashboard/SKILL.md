---
name: dashboard
description: Start the interactive web dashboard to view and compare backtest results
disable-model-invocation: true
---

Start the interactive results dashboard.

1. Check that results exist in the `results/` directory. If not, suggest running `/backtest-all` first.
2. Start the server: `python scripts/serve_results.py`
3. Tell the user to open http://localhost:5000 in their browser
