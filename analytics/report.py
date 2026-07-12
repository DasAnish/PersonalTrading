"""
Static, human-readable per-strategy backtest reports.

Reads whatever has already been written to
``results/strategies/<strategy_key>/`` (via ``backtesting.results_io``,
``scripts/run_all_overfitting.py``) and renders it into a single Markdown
document — metrics table, stress-test crisis/scenario-removal tables, and
overfitting (DSR / PBO / k-fold) verdict cards.

Every section is optional except the header: a strategy that has only run
a plain backtest (no ``--stress-test``, no overfitting analysis) still gets
a report, with the missing sections replaced by a short note explaining how
to generate them. Nothing in this module raises on a missing optional file
— that is the whole point of ``load_strategy_payload`` returning a partial
dict and of the direct ``STRESS_TEST_FILE`` / ``OVERFITTING_FILE`` reads
here checking ``Path.exists()`` first.

Public API:
    build_report(strategy_key, results_dir) -> str        # markdown
    to_html(markdown_str) -> str                           # self-contained HTML
    write_report(strategy_key, results_dir, fmt="md") -> dict[str, Path]
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backtesting.results_schema import (
    OVERFITTING_FILE,
    STRESS_TEST_FILE,
    PathLike,
    load_strategy_payload,
    strategy_dir,
)

# ---------------------------------------------------------------------------
# Small formatting helpers
# ---------------------------------------------------------------------------


def _humanize(key: str) -> str:
    """``max_drawdown_duration_days`` -> ``Max Drawdown Duration Days``."""
    return key.replace("_", " ").strip().title()


def _format_value(value: Any) -> str:
    """Render a metric value for a Markdown table cell."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def _verdict_label(verdict: Optional[str]) -> str:
    if not verdict:
        return "N/A"
    icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(verdict, "")
    return f"{icon} {verdict}".strip()


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    """Render a GitHub-flavoured Markdown pipe table."""
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def _first_last_date(portfolio_history: Optional[list]) -> Optional[tuple]:
    if not portfolio_history:
        return None
    first = portfolio_history[0].get("date") or portfolio_history[0].get("timestamp")
    last = portfolio_history[-1].get("date") or portfolio_history[-1].get("timestamp")
    if not first or not last:
        return None
    return str(first)[:10], str(last)[:10]


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_header(strategy_key: str, payload: Dict[str, Any], target_dir: Path) -> str:
    info = payload.get("info", {})
    name = info.get("display_name") or info.get("name") or strategy_key

    lines = [f"# {name} — Backtest Report", "", f"**Strategy key:** `{strategy_key}`"]

    date_range = _first_last_date(payload.get("portfolio_history"))
    if date_range:
        lines.append(f"**Date range:** {date_range[0]} to {date_range[1]}")
    else:
        lines.append("**Date range:** unknown (no portfolio_history.json)")

    metrics_path = target_dir / "metrics.json"
    if metrics_path.exists():
        run_date = metrics_path.stat().st_mtime
        run_date_str = datetime.fromtimestamp(run_date).strftime("%Y-%m-%d %H:%M")
        lines.append(f"**Run date (results last written):** {run_date_str}")
    else:
        lines.append("**Run date:** unknown")

    if info.get("description"):
        lines.append("")
        lines.append(info["description"])

    return "\n".join(lines)


def _build_metrics_section(payload: Dict[str, Any]) -> str:
    metrics = payload.get("metrics")
    if not metrics:
        return (
            "## Performance Metrics\n\n"
            "_metrics.json not found for this strategy — no metrics to report._"
        )

    rows = [[_humanize(k), _format_value(v)] for k, v in metrics.items()]
    table = _md_table(["Metric", "Value"], rows)
    return f"## Performance Metrics\n\n{table}"


def _build_stress_section(target_dir: Path) -> str:
    path = target_dir / STRESS_TEST_FILE
    if not path.exists():
        return (
            "## Stress Testing\n\n"
            "_Stress test not run for this strategy. Generate it with:_\n"
            "```\npython scripts/run_backtest.py --all --stress-test\n```"
        )

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"## Stress Testing\n\n_Could not read {STRESS_TEST_FILE}: {exc}_"

    lines = ["## Stress Testing"]

    crisis_metrics = data.get("crisis_metrics") or []
    if crisis_metrics:
        rows = [
            [
                m.get("crisis_name", ""),
                f"{m.get('start', '')} to {m.get('end', '')}",
                f"{m.get('sharpe', 0):.3f}",
                f"{m.get('max_drawdown_pct', 0):.2f}%",
                f"{m.get('total_return_pct', 0):.2f}%",
                str(m.get("recovery_days", "N/A")),
                "Yes" if m.get("has_data") else "No",
            ]
            for m in crisis_metrics
        ]
        lines.append("\n### Crisis Period Performance\n")
        lines.append(
            _md_table(
                [
                    "Crisis",
                    "Window",
                    "Sharpe",
                    "Max DD",
                    "Total Return",
                    "Recovery (days)",
                    "Data",
                ],
                rows,
            )
        )
    else:
        lines.append("\n_No crisis metrics available._")

    scenario_removal = data.get("scenario_removal") or []
    if scenario_removal:
        rows = [
            [
                r.get("crisis_name", ""),
                f"{r.get('full_sharpe', 0):.3f}",
                f"{r.get('loo_sharpe', 0):.3f}",
                f"{r.get('sharpe_delta', 0):+.3f}",
            ]
            for r in scenario_removal
        ]
        lines.append("\n### Scenario Removal (Leave-One-Crisis-Out)\n")
        lines.append(
            "_Positive Δ Sharpe means the crisis window helped the strategy's "
            "full-history Sharpe; negative means it hurt it._\n"
        )
        lines.append(
            _md_table(["Crisis", "Full Sharpe", "LOO Sharpe", "Δ Sharpe"], rows)
        )
    else:
        lines.append("\n_No scenario-removal results available._")

    return "\n".join(lines)


def _dsr_lines(dsr: Dict[str, Any]) -> List[str]:
    return [
        "### Deflated Sharpe Ratio (DSR)",
        "",
        _md_table(
            ["Field", "Value"],
            [
                ["DSR", f"{dsr['dsr']*100:.1f}% {_verdict_label(dsr['verdict'])}"],
                ["Observed Sharpe (annualised)", f"{dsr['observed_sharpe']:.3f}"],
                ["Reference Sharpe (deflated)", f"{dsr['sharpe_reference']:.3f}"],
                ["Return Periods (T)", str(dsr["t_periods"])],
                ["Trials (N)", str(dsr["n_trials"])],
                ["Skewness", f"{dsr['skewness']:.3f}"],
                ["Excess Kurtosis", f"{dsr['excess_kurtosis']:.3f}"],
                ["Pass Threshold", f">= {dsr['threshold_pass']*100:.0f}%"],
            ],
        ),
    ]


def _pbo_lines(pbo: Dict[str, Any]) -> List[str]:
    return [
        "### Probability of Backtest Overfitting (PBO)",
        "",
        _md_table(
            ["Field", "Value"],
            [
                ["PBO", f"{pbo['pbo']*100:.1f}% {_verdict_label(pbo['verdict'])}"],
                ["Prob. OOS Loss", f"{pbo['prob_oos_loss']*100:.1f}%"],
                ["CSCV Partitions", f"{pbo['n_combinations']:,}"],
                ["S Subsets", str(pbo["s_subsets"])],
                ["N Configs", str(pbo["n_configs"])],
                ["Pass Threshold", f"<= {pbo['threshold_pass']*100:.0f}%"],
            ],
        ),
    ]


def _kfold_lines(kfold: Dict[str, Any]) -> List[str]:
    fold_sharpes = ", ".join(f"{s:.2f}" for s in kfold.get("fold_sharpes", []))
    return [
        "### K-Fold Temporal Stability",
        "",
        _md_table(
            ["Field", "Value"],
            [
                ["Folds (k)", str(kfold["n_folds"])],
                ["Fold Sharpes", f"[{fold_sharpes}]"],
                [
                    "Mean / Std Sharpe",
                    f"{kfold['mean_sharpe']:.3f} / {kfold['std_sharpe']:.3f}",
                ],
                ["Worst Fold Sharpe", f"{kfold['worst_fold_sharpe']:.3f}"],
                [
                    "Fraction Positive",
                    f"{kfold['fraction_positive']*100:.1f}% {_verdict_label(kfold['verdict'])}",
                ],
                [
                    "Pass Threshold",
                    f">= {kfold['threshold_pass']*100:.0f}% positive folds",
                ],
            ],
        ),
    ]


def _build_overfitting_section(target_dir: Path) -> str:
    path = target_dir / OVERFITTING_FILE
    if not path.exists():
        return (
            "## Overfitting Analysis\n\n"
            "_Overfitting analysis not run for this strategy. Generate it with:_\n"
            "```\npython scripts/run_all_overfitting.py --strategy <key> --n-trials <N>\n```"
        )

    try:
        with open(path, "r") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"## Overfitting Analysis\n\n_Could not read {OVERFITTING_FILE}: {exc}_"

    lines = ["## Overfitting Analysis", ""]
    lines.append(
        f"N parameter combinations tested: {data.get('n_param_combinations', 'N/A')}"
    )
    if data.get("analysis_date"):
        lines.append(f"Analysed: {str(data['analysis_date'])[:10]}")
    lines.append("")

    verdicts = []
    if data.get("dsr"):
        lines.extend(_dsr_lines(data["dsr"]))
        lines.append("")
        verdicts.append(data["dsr"]["verdict"])
    else:
        lines.append("### Deflated Sharpe Ratio (DSR)\n\n_DSR not computed._\n")

    if data.get("pbo"):
        lines.extend(_pbo_lines(data["pbo"]))
        lines.append("")
        verdicts.append(data["pbo"]["verdict"])
    else:
        lines.append(
            "### Probability of Backtest Overfitting (PBO)\n\n_PBO not computed — no return matrix available._\n"
        )

    if data.get("kfold"):
        lines.extend(_kfold_lines(data["kfold"]))
        lines.append("")
        verdicts.append(data["kfold"]["verdict"])
    else:
        lines.append(
            "### K-Fold Temporal Stability\n\n_K-fold stability not computed._\n"
        )

    if verdicts:
        if all(v == "PASS" for v in verdicts):
            overall = "PASS"
        elif any(v == "FAIL" for v in verdicts):
            overall = "FAIL"
        else:
            overall = "WARN"
        lines.append(f"**Overall Overfitting Verdict:** {_verdict_label(overall)}")

    errors = data.get("errors") or []
    if errors:
        lines.append("")
        lines.append("**Errors during analysis:**")
        for e in errors:
            lines.append(f"- {e}")

    return "\n".join(lines)


def _build_completeness_footer(payload: Dict[str, Any], target_dir: Path) -> str:
    def present(flag: bool) -> str:
        return "present" if flag else "absent"

    rows = [
        ["metrics.json", present("metrics" in payload)],
        ["info.json", present("info" in payload)],
        ["portfolio_history.json", present("portfolio_history" in payload)],
        ["transactions.json", present("transactions" in payload)],
        ["weights_history.json", present("weights_history" in payload)],
        [STRESS_TEST_FILE, present((target_dir / STRESS_TEST_FILE).exists())],
        [OVERFITTING_FILE, present((target_dir / OVERFITTING_FILE).exists())],
    ]
    table = _md_table(["File", "Status"], rows)
    return f"## Data Completeness\n\n{table}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_report(strategy_key: str, results_dir: PathLike) -> str:
    """
    Build a full Markdown report for a strategy from whatever result files
    exist under ``<results_dir>/strategies/<strategy_key>/``.

    Never raises on missing optional files (stress_test.json,
    overfitting_analysis.json) — those sections degrade to a short note
    with the command to generate them. Only requires the results directory
    itself; even a strategy with just metrics.json (or nothing at all)
    produces a valid, if sparse, report.

    Args:
        strategy_key: Strategy identifier (directory name under
            ``<results_dir>/strategies/``).
        results_dir: Top-level results directory (e.g. ``Path("results")``).

    Returns:
        Markdown document as a string.
    """
    results_dir = Path(results_dir)
    target_dir = strategy_dir(results_dir, strategy_key)
    payload = load_strategy_payload(results_dir, strategy_key)

    sections = [
        _build_header(strategy_key, payload, target_dir),
        _build_metrics_section(payload),
        _build_stress_section(target_dir),
        _build_overfitting_section(target_dir),
        _build_completeness_footer(payload, target_dir),
    ]

    return "\n\n---\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Markdown -> self-contained HTML
# ---------------------------------------------------------------------------

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE_RE = re.compile(r"`([^`]+?)`")

_HTML_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
       max-width: 900px; margin: 40px auto; padding: 0 20px; color: #1f2933;
       background: #fff; line-height: 1.5; }
h1 { border-bottom: 2px solid #667eea; padding-bottom: 8px; }
h2 { margin-top: 32px; color: #334155; }
h3 { margin-top: 20px; color: #475569; }
table { border-collapse: collapse; width: 100%; margin: 12px 0 20px 0; }
th, td { border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }
th { background: #f1f5f9; }
tr:nth-child(even) { background: #fafafa; }
code, pre { background: #f1f5f9; border-radius: 4px; }
pre { padding: 10px; overflow-x: auto; }
code { padding: 1px 5px; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 24px 0; }
"""


def _inline_md(text: str) -> str:
    text = html.escape(text, quote=False)
    text = _INLINE_CODE_RE.sub(r"<code>\1</code>", text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    return text


def _render_table_block(lines: List[str]) -> str:
    header_cells = [c.strip() for c in lines[0].strip("|").split("|")]
    body_rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        body_rows.append(cells)

    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{_inline_md(c)}</th>" for c in header_cells)
    out.append("</tr></thead><tbody>")
    for row in body_rows:
        out.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def to_html(markdown_str: str) -> str:
    """
    Convert the Markdown produced by ``build_report`` into a small,
    self-contained HTML document (inline CSS, no external requests, no
    JavaScript).

    Deliberately not a general-purpose Markdown renderer — it only covers
    the subset ``build_report`` emits: ``#``/``##``/``###`` headers, pipe
    tables, ``-`` bullet lists, fenced code blocks, ``**bold**``/`` `code` ``
    inline spans, ``---`` horizontal rules, and plain paragraphs. This
    avoids adding a new third-party dependency (the ``markdown`` package
    is not in this project's dependencies).
    """
    lines = markdown_str.split("\n")
    html_parts: List[str] = []
    i = 0
    n = len(lines)
    in_code_block = False
    code_lines: List[str] = []

    while i < n:
        line = lines[i]

        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lines = []
            else:
                in_code_block = False
                code_text = html.escape("\n".join(code_lines), quote=False)
                html_parts.append(f"<pre><code>{code_text}</code></pre>")
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            html_parts.append("<hr>")
            i += 1
            continue

        if stripped.startswith("#"):
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            text = stripped[level:].strip()
            html_parts.append(f"<h{level}>{_inline_md(text)}</h{level}>")
            i += 1
            continue

        if stripped.startswith("|"):
            table_lines = [stripped]
            j = i + 1
            while j < n and lines[j].strip().startswith("|"):
                table_lines.append(lines[j].strip())
                j += 1
            if len(table_lines) >= 2:
                html_parts.append(_render_table_block(table_lines))
            i = j
            continue

        if stripped.startswith("- "):
            items = []
            j = i
            while j < n and lines[j].strip().startswith("- "):
                items.append(lines[j].strip()[2:])
                j += 1
            html_parts.append(
                "<ul>" + "".join(f"<li>{_inline_md(it)}</li>" for it in items) + "</ul>"
            )
            i = j
            continue

        # Plain paragraph
        html_parts.append(f"<p>{_inline_md(stripped)}</p>")
        i += 1

    body = "\n".join(html_parts)
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Strategy Report</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        "</head>\n<body>\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )


def write_report(
    strategy_key: str,
    results_dir: PathLike,
    fmt: str = "md",
) -> Dict[str, Optional[Path]]:
    """
    Build and write a strategy report to
    ``<results_dir>/strategies/<strategy_key>/report.md`` (and/or
    ``report.html``).

    Args:
        strategy_key: Strategy identifier.
        results_dir: Top-level results directory.
        fmt: One of ``"md"`` (default), ``"html"``, or ``"both"``.

    Returns:
        Dict with keys ``"md"`` and ``"html"`` mapping to the written
        ``Path`` (or ``None`` if that format wasn't requested).
    """
    if fmt not in ("md", "html", "both"):
        raise ValueError(f"fmt must be 'md', 'html', or 'both', got {fmt!r}")

    results_dir = Path(results_dir)
    target_dir = strategy_dir(results_dir, strategy_key)
    target_dir.mkdir(parents=True, exist_ok=True)

    markdown_str = build_report(strategy_key, results_dir)

    written: Dict[str, Optional[Path]] = {"md": None, "html": None}

    if fmt in ("md", "both"):
        md_path = target_dir / "report.md"
        md_path.write_text(markdown_str, encoding="utf-8")
        written["md"] = md_path

    if fmt in ("html", "both"):
        html_path = target_dir / "report.html"
        html_path.write_text(to_html(markdown_str), encoding="utf-8")
        written["html"] = html_path

    return written
