#!/usr/bin/env python
"""Poll dashboard job pipelines until all reach a terminal state.

Designed to be driven by the Claude Code `Monitor` tool during a
build-strategies Phase 3: each printed line is a Monitor event, and the final
`ALL DONE` line (emitted just before exit) wakes the conversation so the
orchestrator can collect results.

Usage:
    python scripts/wait_jobs.py <job_id> [<job_id> ...]
    python scripts/wait_jobs.py --interval 20 <job_id> ...

Terminal states: done, failed, interrupted. Unknown job ids are treated as
terminal (reported once) so a typo can't hang the watch forever.
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.request
import json

BASE = "http://localhost:5000/api/run/status/"
TERMINAL = {"done", "failed", "interrupted", "unknown"}


def poll(job_id: str) -> str:
    try:
        with urllib.request.urlopen(f"{BASE}{job_id}", timeout=10) as r:
            payload = json.load(r)
    except urllib.error.HTTPError as e:
        # 404 == unknown job id (server responds with a JSON error body) —
        # treat as terminal so a typo can't hang the watch forever.
        if e.code == 404:
            return "unknown"
        return f"error:HTTP{e.code}"
    except Exception as e:  # network/server hiccup — report, keep waiting
        return f"error:{type(e).__name__}"
    if payload.get("error"):
        return "unknown"
    return payload.get("state", "running")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("job_ids", nargs="+")
    ap.add_argument("--interval", type=float, default=20.0,
                    help="seconds between poll rounds (default 20)")
    ap.add_argument("--max-rounds", type=int, default=180,
                    help="give up after this many rounds (default 180)")
    args = ap.parse_args()

    pending = list(dict.fromkeys(args.job_ids))  # dedupe, keep order
    for rnd in range(1, args.max_rounds + 1):
        states = {j: poll(j) for j in pending}
        done = [j for j, s in states.items() if s in TERMINAL]
        still = [j for j, s in states.items() if s not in TERMINAL]
        # one status line per round (a Monitor event)
        summary = ", ".join(f"{j[:8]}={states[j]}" for j in pending)
        print(f"[round {rnd}] {len(still)} running | {summary}", flush=True)
        pending = still
        if not pending:
            outcomes = ", ".join(f"{j[:8]}={states.get(j, '?')}" for j in done)
            print(f"ALL DONE ({len(done)} terminal): {outcomes}", flush=True)
            return 0
        time.sleep(args.interval)

    print(f"TIMEOUT: {len(pending)} still running after {args.max_rounds} "
          f"rounds: {', '.join(j[:8] for j in pending)}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
