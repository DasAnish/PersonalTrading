#!/usr/bin/env python3
"""
Export the read-only dashboard to a static site bundle.

The viewing surface of the dashboard (overview, per-strategy pages, validation,
info, and every read-only ``/api/*`` endpoint) is deterministic over the JSON
already sitting under ``results/`` — no live compute is needed to *view* it. This
script drives ``create_app()`` through Flask's in-process test client (no network,
no port) and writes each response to a folder that any static host can serve.

    python scripts/export_static_site.py --out site
    # then, to prove it needs no backend:
    python -m http.server 8000 --directory site

What it does NOT export (out of scope for a view-only static bundle):
  - the job runner  (/api/run/*  — spawns heavy subprocesses)
  - live-IB risk    (/live-risk, /api/live-risk, blend/target-allocation)

Path scheme
-----------
Every response body is written to ``<url-path>/index.html`` and served via
directory-index resolution. This is the one scheme that avoids leaf/prefix
filename collisions (``/api/strategies`` is BOTH a leaf and the prefix of
``/api/strategies/summary``) while letting the existing frontend keep fetching
its exact ``/api/...`` URLs unchanged — ``response.json()`` ignores content-type,
so JSON living in an ``index.html`` parses fine.

The only endpoints the frontend reaches with a query string — rolling metrics and
CSV export — can't round-trip through a static host (it ignores the query). Those
are pre-expanded here into flat sub-paths, and ``static/js/api.js`` rewrites the
two call sites to match when ``window.STATIC_MODE`` is set.

NOTE: this is read-only export tooling. It never touches IB or places orders.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Mirror serve_results.py: scripts/ on path for the server package, repo root
# on path so server/data.py can import the top-level backtesting package.
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from server.app import create_app  # noqa: E402
from server.data import list_strategy_keys  # noqa: E402

# Kept in sync with the <select> options in templates/strategy.html (Rolling tab).
ROLLING_METRICS = ("sharpe", "volatility", "sortino")
ROLLING_WINDOWS = (21, 63, 126, 252)
EXPORT_TYPES = ("portfolio", "transactions", "weights")

STATIC_FLAG = "<script>window.STATIC_MODE=true;</script>"


def _write(out_dir: Path, url_path: str, body: bytes, *, is_page: bool) -> None:
    """Write one response body under ``<out>/<url-path>/index.html``.

    For HTML pages we inject the STATIC_MODE flag so the query-string call
    sites (rolling, export) switch to the flat static paths produced below.
    """
    rel = url_path.strip("/")
    dest = out_dir / rel / "index.html"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_page:
        html = body.decode("utf-8")
        if STATIC_FLAG not in html:
            html = html.replace("</head>", STATIC_FLAG + "</head>", 1)
        body = html.encode("utf-8")
    dest.write_bytes(body)


def _get(client, path: str):
    """GET a path via the test client; return (status_code, body_bytes)."""
    resp = client.get(path)
    return resp.status_code, resp.get_data()


def export(out_dir: Path) -> dict:
    """Render the read-only dashboard into ``out_dir``. Returns a small stat dict."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    app = create_app()
    client = app.test_client()
    stats = {"pages": 0, "api": 0, "csv": 0, "skipped": 0, "strategies": 0}

    # --- static assets: copy verbatim (css, js, vendored chart.min.js) ---------
    static_src = Path(__file__).parent / "server" / "static"
    shutil.copytree(static_src, out_dir / "static")

    # --- library-wide HTML pages ----------------------------------------------
    for path in ("/", "/validation", "/info"):
        code, body = _get(client, path)
        if code == 200:
            _write(out_dir, path, body, is_page=True)
            stats["pages"] += 1

    # --- library-wide API ------------------------------------------------------
    for path in (
        "/api/strategies",
        "/api/strategies/summary",
        "/api/validation-summary",
        "/api/data-freshness",
    ):
        code, body = _get(client, path)
        if code == 200:
            _write(out_dir, path, body, is_page=False)
            stats["api"] += 1

    # --- per-strategy pages + API ---------------------------------------------
    keys = list_strategy_keys()
    stats["strategies"] = len(keys)
    for key in keys:
        code, body = _get(client, f"/strategy/{key}")
        if code == 200:
            _write(out_dir, f"/strategy/{key}", body, is_page=True)
            stats["pages"] += 1

        # Always-present JSON (200) and best-effort analyses (404 when a step
        # has not been run — we deliberately DON'T write those, so the static
        # host returns a real 404 and the frontend's "not run yet" UI fires,
        # exactly as it does against the live server).
        for suffix in ("", "/monthly_returns", "/overfitting", "/stress_test"):
            p = f"/api/strategy/{key}{suffix}"
            code, body = _get(client, p)
            if code == 200:
                _write(out_dir, p, body, is_page=False)
                stats["api"] += 1
            else:
                stats["skipped"] += 1

        # Rolling: pre-expand the finite metric x window grid to flat sub-paths.
        for metric in ROLLING_METRICS:
            for window in ROLLING_WINDOWS:
                p = f"/api/strategy/{key}/rolling?metric={metric}&window={window}"
                code, body = _get(client, p)
                if code == 200:
                    flat = f"/api/strategy/{key}/rolling/{metric}_{window}"
                    _write(out_dir, flat, body, is_page=False)
                    stats["api"] += 1
                else:
                    stats["skipped"] += 1

        # CSV export: real files with a .csv extension (no dir-index needed).
        for etype in EXPORT_TYPES:
            code, body = _get(client, f"/api/strategy/{key}/export?type={etype}")
            if code == 200:
                dest = out_dir / "api" / "strategy" / key / "export" / f"{etype}.csv"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body)
                stats["csv"] += 1
            else:
                stats["skipped"] += 1

    # --- Cloudflare Pages _headers: correct content-types (cosmetic; the JS
    #     parses regardless). Long-cache the fingerprint-free static assets. ---
    (out_dir / "_headers").write_text(
        "/api/*\n  Content-Type: application/json\n"
        "/static/*\n  Cache-Control: public, max-age=86400\n",
        encoding="utf-8",
    )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="site",
        help="Output directory for the static bundle (default: site).",
    )
    args = parser.parse_args()

    out_dir = Path(args.out).resolve()
    print(f"[*] Exporting static dashboard to {out_dir}")
    stats = export(out_dir)
    print(
        f"[+] Done: {stats['strategies']} strategies -> "
        f"{stats['pages']} pages, {stats['api']} api files, "
        f"{stats['csv']} csv ({stats['skipped']} not-run endpoints skipped)."
    )
    print(f"[*] Preview: python -m http.server 8000 --directory {out_dir}")


if __name__ == "__main__":
    main()
