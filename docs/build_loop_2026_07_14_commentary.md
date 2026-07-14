# Build-Loop Commentary — 2026-07-14

Commentary on the research-scan → build-strategies loop run on 2026-07-14
(commits `9c8836f`..`ef01d35`, 29 commits). Written after the run, so it may
compare results against the pre-registered hypotheses; the hypotheses
themselves (in `research/ideas/*.md`) were frozen before each backtest.

> **CORRECTION (post-run, after the nightly re-backtest).** The nightly
> full-universe run exposed a read-only-numpy-view bug in
> `FlexibleAssetAllocationStrategy` (`corr = returns.corr().values` mutated in
> place): at some rebalances it silently fell back to equal weight, which
> **inflated every FAA result**. After the fix (commit on 2026-07-14), **no FAA
> variant passes** — the best is `flexible_asset_allocation_theme_defensive_volheavy`
> at Sharpe 1.75 (WARN); the previously-reported flagship
> `flexible_asset_allocation_theme_defensive_126d` "2.76" is **now 1.21 (FAIL)**.
> The sections below have been corrected. The true library leaders are the
> risk-parity / regime classes (which are bug-free), not FAA. Treat this as the
> headline lesson of the run: a spectacular backtest was a bug artifact, and only
> a second, independent full re-run caught it.

## 1. Scope

- **88 new strategy definitions** added across 27 loop iterations.
- Verdicts read directly from `results/strategies/<key>/validation.json`, never
  from a builder's report. The pre-correction tally was 43 PASS / 19 WARN /
  26 FAIL; **after the FAA bug fix, ~14 former FAA PASS/WARN entries drop, so the
  corrected tally is roughly 29 PASS / 21 WARN / 38 FAIL** (re-run the SPA/battery
  for the exact live count).
- Library grew from ~300 to **343** definitions.
- ~20 genuinely new **mechanisms** (new Python classes), the rest are
  universe/parameter variants of those.
- Sources: every idea is tied to a real paper (arXiv/SSRN/JF/JFE/RFS/FAJ/JPM
  etc.); no fabricated citations. Rejected ideas are kept in the library with a
  `rejected` verdict rather than deleted, so the negative results are on record.

## 2. New validated mechanisms, by family

**Risk-based construction (the most productive vein)**
- `minimum_cvar` — Rockafellar & Uryasev (2000) tail-risk LP. Full universe 1.60.
- `minimum_semivariance` — Estrada (2008) downside-covariance QP.
- `minimum_cdar` — Chekhlov/Uryasev/Zabarankin (2005) path-dependent drawdown. 1.14.
- `downside_risk_parity` — Roncalli (2013) semicovariance risk budgeting. 1.56.
- `cvar_risk_parity` — Boudt/Peterson/Croux (2008) component-CVaR budgeting. **1.77**.
- `min_var_shrinkage` — Ledoit & Wolf (2004) shrinkage covariance. **1.67**.
- `inverse_volatility` — Leote de Carvalho et al (2012) naive risk parity. **1.72**.

**Regime & hedging**
- `stock_bond_correlation_regime` — Brixton et al / AQR (2023). **1.82** (top regime).
- `defensive_asset_allocation_canary` — Keller & Keuning (2018) DAA. 1.24.
- `dynamic_crisis_hedge_trend` — Harvey et al (2019), overlay. 1.55.
- `treasury_flight_to_quality_hedge` — flight-to-quality overlay. 1.53.

**Momentum & mean-reversion**
- `flexible_asset_allocation` — Keller & van Putten (2012) generalized momentum.
  **Corrected:** after the read-only bug fix no FAA variant passes; best is
  `theme_defensive_volheavy` at 1.75 (WARN). The mechanism is marginal on this
  universe, not the flagship the buggy run suggested.
- `short_term_reversal` — Jegadeesh (1990) 1-month reversal. 1.46.
- `residual_momentum` — Blitz/Huij/Martens (2011). 1.27.
- `national_market_mean_reversion` — Balvers/Wu/Gilliland (2000). 1.31.
- `gold_silver_ratio_mean_reversion` — Escribano & Granger (1998). 1.24 (but -24% DD).

**Low-risk / defensive tilts**
- `low_ivol_tilt` — Ang/Hodrick/Xing/Zhang (2006). 1.47.
- `downside_beta_tilt` — Ang/Chen/Xing (2006). 0.83 (WARN).
- `low_max_tilt` — Bali/Cakici/Whitelaw (2011). 0.97 (WARN).

**Meta**
- `strategy_level_risk_parity_ensemble` — Qian (2005) inverse-vol meta. 1.07 (WARN).

## 3. What worked, what didn't — the empirical pattern

1. **Universe composition matters more than universe size.** Narrow single-sleeve
   groups (`em_equity`, `theme_real_assets`, `commodity`, `macro_3`) consistently
   FAILED validation, while broad or mixed-class groups did better. The original
   write-up leaned on FAA-on-`theme_defensive` (2.76) as the proof point; that
   number was a bug artifact, so the evidence is weaker than first claimed —
   composition still clearly matters (the risk-parity family all peak on the full,
   mixed universe), but the dramatic FAA figure should be ignored.

2. **Downside/tail-risk optimizers want breadth.** `minimum_cvar` went 1.17
   (core_8) → **1.60** (full universe); `minimum_semivariance` went WARN → PASS on
   the full universe. More assets give these methods more tail-diversifiers to work
   with.

3. **Risk-based construction beats signal rotation on this universe.** Every
   equal-risk / min-risk / inverse-vol / shrinkage construction validated; every
   concentrated top-N momentum rotation FAILED (`accelerating_dual_momentum`,
   `sharpe_momentum`, `vigilant_asset_allocation`) — too concentrated and
   turnover-heavy on only ~13 asset-class ETFs.

4. **Meta-blends fail the deflated-Sharpe battery.** The library already holds
   ~40 meta portfolios, so the DSR multiplicity penalty is harsh; only
   `meta_downside_risk_suite` cleared to WARN. Blending is not where the marginal
   value is here.

5. **Naive beats optimized.** `inverse_volatility` (no optimization, no
   covariance) scored 1.72 — within a whisker of every optimized construction
   method — echoing DeMiguel/Garlappi/Uppal's "optimal versus naive" result. That
   is itself a warning sign (see caveats).

## 4. Standouts and honest caveats

**Standouts (corrected — high Sharpe + shallow drawdown + clean DSR, FAA excluded):**
`stock_bond_correlation_regime` (1.82 / -4.6% / DSR 0.99),
`cvar_risk_parity` (1.77 / -2.4% / 0.998), `inverse_volatility` (1.72 / 0.997),
`min_var_shrinkage` (1.67 / 0.997), `minimum_cvar_full` (1.60 / 0.95),
`downside_risk_parity` (1.56 / 0.99). These are the true leaders; all are
risk-parity / regime classes that do not use the buggy FAA code path.

**Caveats — read before trusting any of these:**

- **A headline result was a bug (the single most important caveat).** The
  original "best strategy, Sharpe 2.76" was an artifact of a silent equal-weight
  fallback in FAA. It survived the entire per-strategy DSR/PBO/k-fold battery and
  was only caught by an independent full re-backtest (the nightly). Assume other
  latent bugs of this kind may exist in the haiku-built classes; a green
  validation verdict is not proof the code is correct.

- **The library-wide SPA is underpowered.** `results/spa_analysis.json` reports
  `n_obs = 12` — the multiple-testing test that is meant to be the go/no-go has
  only twelve observations. So the *per-strategy* DSR/PBO/k-fold battery is doing
  the real work here; the library SPA is not yet a reliable arbiter. This is the
  long-standing "SPA blocked by short T" issue in the session log, not new.

- **These results share a common defensive bias.** Almost every winner loads
  heavily on bonds (VUTY/AGGU) and gold (SGLN). Over the 2016–2026 sample that was
  a tailwind for most of the window. The high Sharpes and 2–5% drawdowns partly
  reflect a benign regime for defensive assets, not pure skill — and 2022 (bonds
  and equities down together) is only one episode in the sample. Expect materially
  worse live behaviour in a sustained bond bear market.

- **The winners are highly correlated with each other.** `inverse_volatility`,
  `min_var_shrinkage`, `cvar_risk_parity`, `downside_risk_parity` are five names
  for "hold mostly bonds/gold weighted by low risk." They should **not** be
  treated as independent bets — a portfolio of all of them is close to a single
  defensive allocation.

- **A few high-Sharpe names hide large drawdowns.** The gold-silver ratio variants
  post Sharpe ~1.2–1.4 but with **-19% to -24%** max drawdowns — very different
  risk from the 2–3% construction strategies at similar Sharpe.

- **WARN ≠ endorsed.** 19 strategies are WARN (built, not FAIL). They are kept for
  completeness but are marginal; do not read the table as 62 recommendations.

- **Novelty is now exhausted.** Iterations 21–27 reached standard textbook
  construction methods. Further loop iterations would be increasingly incremental
  re-weightings of the same defensive assets.

## 5. Recommendations

1. **Do not deploy on Sharpe rank.** Pick 2–3 genuinely *distinct* mechanisms
   (e.g. one construction like `cvar_risk_parity`, one regime like
   `stock_bond_correlation_regime`, one signal like `short_term_reversal`) rather
   than a basket of correlated risk-based clones.
2. **Fix the SPA power problem before trusting any ranking.** The library-wide
   go/no-go needs a longer observation window (`n_obs = 12` is not enough to
   separate 340 strategies). Until then, lean on per-strategy DSR + out-of-universe
   / walk-forward tests.
3. **Stress-test the defensive bias.** Re-run the top names on a bond-bear
   sub-sample (e.g. 2021-2023) to see how much of the edge survives without the
   bond tailwind.
4. **Stop adding correlated construction variants.** The marginal one adds library
   clutter and worsens the multiplicity penalty, not diversification.
