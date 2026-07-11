# live_tracking/

Snapshots of the real (manually-traded) portfolio over time, used to track live performance against backtests. **Machine-written** by the snapshot scripts.

- `nav_history.csv` — appended NAV snapshots (one row per snapshot)
- `positions/` — dated position snapshots, e.g. `2026-07-11.json`

Written by `scripts/snapshot_nav.py` and `scripts/snapshot_positions.py`. Feeds the dashboard's live-risk view. No orders are placed — this only records state the user entered manually.
