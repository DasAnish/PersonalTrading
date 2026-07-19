---
title: Momentum Crash Management (bear-state exposure scaling)
source: Daniel & Moskowitz (2016), Journal of Financial Economics 122(2) — Momentum Crashes
mechanism: momentum-cs
status: built
date_added: 2026-07-20
---

## Hypothesis (pre-registered)

Daniel & Moskowitz (JFE 2016) show momentum strategies suffer rare, severe
crashes that are forecastable: they occur in panic states — after multi-year
market declines when ex-ante volatility is high — as the momentum portfolio
becomes effectively short a call option on the rebounding market. A dynamic
strategy scaling momentum exposure by forecast return/variance roughly doubles
the momentum Sharpe in their sample. Long-only adaptation: our momentum_top2
family holds recent winners, which in a panic state are crowded defensives that
lag violent rebounds. Pre-registered expectation: scaling momentum_top2_1m
(current SPA best, Sharpe ~1.2) down in bear+high-vol states and diverting to
equal weight should cut its worst drawdown materially while keeping or
improving Sharpe; if panic states are too rare in a 9y window the scaling will
be inert and results match plain momentum — the null being tested.

## Rule sketch

- Bear indicator: trailing 504d (24m) return of the equity sleeve mean
  (VUSA, IWRD, EQQQ) < 0.
- Panic vol: trailing 63d equity-sleeve vol above its trailing 252d median.
- Exposure to the momentum sleeve: 1.0 normally; 0.5 if bear; 0.0 if bear AND
  panic vol — the freed weight goes to equal-weight across the full universe
  (rebound participation), not to cash.
- Momentum sleeve: top-2 by 21d return (mirrors momentum_top2_1m), inverse-vol
  weighted. Monthly; universe core_8.

## Universe fit

Long-only monthly from daily closes; nothing missing. Doesn't fit: the paper's
long-short WML construction — long-only winners proxy the crash exposure only
partially, so effect size should be smaller than the paper's doubling.
