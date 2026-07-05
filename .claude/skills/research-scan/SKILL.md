---
name: research-scan
description: Web-scan quant research sources for new trading strategy ideas and add them to the research backlog
argument-hint: [optional topic scope]
---

> **HARD constraints (research only):** This skill must never modify anything
> under `strategy_definitions/`, must never run a backtest, and must never
> place, submit, modify, or cancel any trade order, or suggest doing so
> programmatically. It only reads quant research sources and writes idea
> files under `research/`.

Scan quant research sources for new strategy ideas and add well-formed
candidates to the research backlog described in `research/README.md`.

1. **Determine scope.** If an argument is provided (e.g.
   `/research-scan carry strategies`), use it to narrow the web search to that
   topic. If no argument is provided, run a broad scan across the mechanism
   taxonomy in `research/README.md` (trend, momentum-cs, mean-reversion,
   carry, vol-premium, diversification, regime, hedging-overlay, seasonality,
   meta), favoring mechanisms that look under-represented in the current
   backlog.

2. **Search quant sources** using WebSearch/WebFetch. Prioritize:
   - arXiv q-fin (arxiv.org, category q-fin.*)
   - SSRN (papers.ssrn.com)
   - AQR Capital Management publications (aqr.com)
   - Robeco quant research (robeco.com)
   - Man Institute / Man Group research (man.com)
   - Alpha Architect blog/research (alphaarchitect.com)
   - Other reputable quant blogs/publications when they cite or summarize
     peer-reviewed or well-known working-paper research

3. **For each promising idea found**, extract:
   - The core mechanism (map it to exactly one tag from the fixed taxonomy
     in `research/README.md` — do not invent new tags)
   - The trading rule (signal, rebalance frequency, parameters)
   - The economic rationale (why the edge should exist: risk premium,
     behavioural bias, structural/flow-based reason)

4. **Dedupe before writing anything.** Read `research/backlog.md` in full and
   skim `strategy_definitions/` (allocations/, composed/, portfolios/) and
   `docs/strategies.md`. Skip any idea that:
   - Already has a row in `research/backlog.md` (same or equivalent
     mechanism/rule — not just a different paper making the same claim), or
   - Is already implemented as a strategy in `strategy_definitions/` or
     `strategies/` (check the mechanism against what's already covered, e.g.
     trend-following, cross-sectional momentum, dual momentum, HRP/risk
     parity, minimum variance, mean reversion (z-score), vol-targeting
     overlays, protective/defensive asset allocation, skewness weighting,
     adaptive asset allocation — see `docs/strategies.md` for the full list).

5. **For each surviving idea, write `research/ideas/<slug>.md`** following the
   exact schema in `research/README.md`:
   - Frontmatter: `title`, `source` (a real URL, or `Author (Year), Venue` —
     never fabricate a citation; if you cannot confirm a source is real, do
     not include the idea), `mechanism` (one taxonomy tag), `status: new`,
     `date_added` (today's date, YYYY-MM-DD).
   - Body with the exact headings `## Hypothesis (pre-registered)`,
     `## Rule sketch`, `## Universe fit`.
   - Critically: write the hypothesis section **before** any backtest exists
     for the idea — this skill never runs backtests, so that's automatic —
     and write it from the source material's own findings and economic
     reasoning, not from a guess at what a backtest would show. Do not soften
     or hedge the expected-Sharpe range after the fact; state it plainly as a
     pre-registered expectation.
   - Universe fit must reference this repo's 13-ETF universe: VUSA (S&P 500),
     EQQQ (Nasdaq-100), IWRD (MSCI World), IMEU (MSCI Europe), IIND (MSCI
     India), AIGC (AI/tech theme), VUTY (US Treasuries GBP-hedged), SGLN
     (physical gold), SSLN (physical silver), BRNT (Brent oil), CRUD (WTI
     oil), COMM/WCOA (broad commodities) — and must be implementable
     **long-only with monthly rebalancing** on this universe. Note explicitly
     what doesn't fit (e.g. no futures curve for carry, no implied-vol
     instrument for vol-regime signals).

6. **Add a row to `research/backlog.md`** for each new idea file: `| [Title](ideas/<slug>.md) | mechanism | new | Source | date_added |`.

7. **Cap this run at ~5 new ideas.** Prefer breadth (a few well-sourced,
   clearly-differentiated ideas) over volume. If more than 5 strong
   candidates are found, keep the 5 most differentiated from the existing
   backlog and mention the rest in your final summary to the user without
   writing files for them.

8. **Report back to the user**: list each new idea file written, its
   mechanism tag, its source, and a one-line summary of the hypothesis. Also
   note any candidates you deliberately skipped as duplicates and why.
