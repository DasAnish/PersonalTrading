# Research Backlog

This directory holds a reviewable backlog of trading-strategy ideas sourced from
published quant research, kept separate from the strategy pipeline itself.
**No idea file here implies a strategy has been built or validated** — it only
means the hypothesis has been recorded. Turning an idea into a live strategy is
a separate, deliberate step handled by the strategy pipeline (`build-strategies`
skill), not by this backlog.

## Pre-registration principle

**The hypothesis is written down BEFORE any backtest exists, and it is never
edited afterward.**

This exists to prevent hindsight bias: if you write "expected Sharpe 0.4–0.7"
only after seeing a backtest that returned 0.6, the number is worthless as
evidence. The `## Hypothesis (pre-registered)` section must be filled in from
economic reasoning and the source paper's own findings alone, before
`strategy_definitions/` gains a matching file. Once a backtest exists, the
hypothesis section is frozen — any commentary on how the backtest compared to
the hypothesis belongs in the validation battery's output or in
`decisions/`, not as an edit to this file.

## Idea file schema

Each idea lives at `research/ideas/<slug>.md` and has two parts.

### Frontmatter (YAML)

```yaml
---
title: Human-readable idea name
source: Author (Year), Venue        # or a URL if the source is a blog/web page
mechanism: momentum-cs               # one tag from the fixed taxonomy below
status: new                          # new | candidate | built | validated | rejected
date_added: 2026-07-05                # YYYY-MM-DD
---
```

| Field | Meaning |
|-------|---------|
| `title` | Short descriptive name of the idea. |
| `source` | Either a URL, or `Author (Year), Venue` for a paper/book (e.g. `Antonacci (2014), McGraw-Hill`). Never fabricate a citation — if unsure a paper exists, don't cite it. |
| `mechanism` | Exactly one tag from the taxonomy below. Pick the closest fit. |
| `status` | Current position in the status lifecycle (see below). |
| `date_added` | The date the idea file was first created. |

### Mechanism taxonomy (fixed vocabulary)

Use exactly one of these tags — do not invent new ones:

- `trend` — time-series trend/momentum on a single asset (price vs. its own history)
- `momentum-cs` — cross-sectional momentum / relative-strength ranking across assets
- `mean-reversion` — betting on reversal to a mean (z-score, short-term reversal)
- `carry` — return from holding a positive-yield/roll-yield position
- `vol-premium` — harvesting the volatility risk premium or vol-targeting exposure
- `diversification` — risk-based allocation (HRP, risk parity, minimum variance)
- `regime` — allocation that switches behaviour based on a detected market regime
- `hedging-overlay` — a tilt/overlay added to protect against a specific risk (e.g. crisis hedge)
- `seasonality` — calendar-based effects (month-of-year, day-of-week, etc.)
- `meta` — combining/ensembling other strategies

### Body sections (exact headings)

```markdown
## Hypothesis (pre-registered)

What edge is being harvested, why it should exist economically (risk premium,
behavioural bias, structural/flow-based reason), the expected Sharpe ratio
range, and which assets/asset classes it should show up on. Written before any
backtest.

## Rule sketch

The trading signal, the rebalance rule (this repo rebalances monthly), and the
parameters involved with plausible ranges (not fitted values).

## Universe fit

Which of the 13 UK-listed ETFs in this repo's universe the idea maps to
(VUSA, EQQQ, IWRD, IMEU, IIND, AIGC, VUTY, SGLN, SSLN, BRNT, CRUD, COMM/WCOA),
and what's missing or imperfect about the fit (e.g. no futures curve for a
carry idea, no VIX-like instrument for a vol-regime idea).
```

## Status lifecycle

```
new  --(strategist picks it up)-->  candidate  --(definition/backtest built)-->  built  --(validation battery runs)-->  validated | rejected
```

- **new** — idea recorded, hypothesis pre-registered, nothing built yet.
- **candidate** — a strategist has picked the idea up and is actively working
  towards a `strategy_definitions/` implementation.
- **built** — a strategy definition and backtest exist for the idea.
- **validated** — the idea passed this repo's overfitting/validation battery
  (see `docs/overfitting.md`).
- **rejected** — the idea was built and failed validation, or was assessed and
  ruled out before building.

## Index

See `research/backlog.md` for the full table of ideas and their current
status. It is maintained by the `/research-scan` skill and updated manually
when an idea's status changes during the build pipeline.
