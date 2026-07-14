# Idea Backlog

This index is maintained by the `/research-scan` skill (which appends rows for
new ideas it finds) and by the strategy build pipeline (which updates the
`Status` column as an idea moves from `new` through `candidate`, `built`, and
finally `validated`/`rejected` — see `research/README.md` for the full status
lifecycle and the idea-file schema). Each row links to the corresponding file
in `research/ideas/`.

| Idea | Mechanism | Status | Source | Added |
|------|-----------|--------|--------|-------|
| [Dual Momentum (relative + absolute)](ideas/dual-momentum.md) | momentum-cs | built | Antonacci (2014), McGraw-Hill | 2026-07-05 |
| [Gold as a Conditional Safe-Haven Hedge](ideas/gold-safe-haven-hedge.md) | hedging-overlay | validated | Baur & Lucey (2010), The Financial Review | 2026-07-05 |
| [Halloween Indicator ("Sell in May") seasonal rotation](ideas/halloween-seasonality.md) | seasonality | rejected | Bouman & Jacobsen (2002), American Economic Review | 2026-07-05 |
| [Cross-Asset Carry (ex-ante yield ranking)](ideas/cross-asset-carry.md) | carry | validated | Koijen, Moskowitz, Pedersen & Vrugt (2018), JFE 127(2) | 2026-07-05 |
| [Low-Beta Defensive Tilt (long-only BAB)](ideas/low-beta-defensive-tilt.md) | vol-premium | validated | Frazzini & Pedersen (2014), JFE 111(1) | 2026-07-05 |
| [Maximum Diversification Portfolio](ideas/maximum-diversification.md) | diversification | rejected | Choueifaty & Coignard (2008), JPM 35(1) | 2026-07-08 |
| [52-Week High Momentum](ideas/52-week-high-momentum.md) | momentum-cs | validated | George & Hwang (2004), JF 59(5) | 2026-07-08 |
| [Volatility / Reward-to-Risk Timing](ideas/volatility-timing.md) | regime | rejected | Kirby & Ostdiek (2012), JFQA 47(2) | 2026-07-08 |
| [Long-Term Reversal (Overreaction)](ideas/long-term-reversal.md) | mean-reversion | rejected | De Bondt & Thaler (1985), JF 40(3) | 2026-07-08 |
| [Simple Moving-Average Trend Filter (Faber Tactical Timing)](ideas/sma-trend-filter.md) | trend | rejected | Faber (2007), Journal of Wealth Management | 2026-07-08 |
| [Strategy-Level Risk Parity Ensemble](ideas/strategy-level-risk-parity-ensemble.md) | meta | validated | Qian (2005), PanAgora Asset Management | 2026-07-08 |
| [Treasury Flight-to-Quality Hedge Overlay](ideas/treasury-flight-to-quality-hedge.md) | hedging-overlay | validated | ScienceDirect — Stock-bond dependence and flight to/from quality | 2026-07-08 |
| [Presidential Election Cycle Seasonality](ideas/presidential-election-cycle.md) | seasonality | candidate | Herbst & Slinkman (1984), Financial Analysts Journal 40(2) | 2026-07-08 |
| [Residual (Idiosyncratic) Momentum](ideas/residual-momentum.md) | momentum-cs | validated | Blitz, Huij & Martens (2011), Journal of Empirical Finance 18(3) | 2026-07-08 |
| [National-Market Mean Reversion (Parametric Contrarian)](ideas/national-market-mean-reversion.md) | mean-reversion | validated | Balvers, Wu & Gilliland (2000), Journal of Finance 55(2) | 2026-07-08 |
| [Low-Volatility Anomaly (The Volatility Effect)](ideas/low-volatility-anomaly.md) | vol-premium | validated | Blitz & van Vliet (2007), Journal of Portfolio Management 34(1) | 2026-07-08 |
| [Accelerating Dual Momentum](ideas/accelerating-dual-momentum.md) | momentum-cs | rejected | Ludlow & Hanly (2018), Engineered Portfolio | 2026-07-08 |
| [Gold Autumn Effect (September/November seasonality)](ideas/gold-autumn-effect.md) | seasonality | validated | Baur (2013), Research in International Business and Finance 27(1) | 2026-07-10 |
| [Stock-Bond Correlation Regime Allocation](ideas/stock-bond-correlation-regime.md) | regime | validated | Brixton, Brooks, Hecht, Ilmanen, Maloney & McQuinn (2023), Financial Analysts Journal | 2026-07-10 |
| [Financial Turbulence (Mahalanobis) Risk-Scaling Overlay](ideas/turbulence-scaled-exposure.md) | hedging-overlay | rejected | Kritzman & Li (2010), Financial Analysts Journal 66(5) | 2026-07-10 |
| [Carry Conditioned on Trend (carry-trend interaction)](ideas/carry-trend-filter.md) | carry | rejected | Baz, Granger, Harvey, Le Roux & Rattray (2015), SSRN 2695101 | 2026-07-10 |
| [Dynamic Crisis Hedge — fast trend selects the defensive asset](ideas/dynamic-crisis-hedge-trend.md) | hedging-overlay | validated | Harvey, Hoyle, Rattray, Sargaison, Taylor & Van Hemert (2019), JPM 45(5) | 2026-07-10 |
| [Time-Series Momentum (vol-scaled trailing-return sign)](ideas/time-series-momentum.md) | trend | validated | Moskowitz, Ooi & Pedersen (2012), JFE 104(2) | 2026-07-13 |
| [Network Risk Parity (graph-theory portfolio construction)](ideas/network-risk-parity.md) | diversification | validated | Journal of Asset Management (2023), s41260-023-00347-8 | 2026-07-13 |
| [Commodity Return Seasonality (calendar-month cross-sectional tilt)](ideas/commodity-return-seasonality.md) | seasonality | validated | Return seasonality in commodity futures, IREF (2024) | 2026-07-13 |
| [Risk-Managed Momentum (volatility-scaled exposure)](ideas/risk-managed-momentum.md) | vol-premium | rejected | Barroso & Santa-Clara (2015), JFE 116(1) | 2026-07-13 |
| [Flexible Asset Allocation (Generalized Momentum)](ideas/flexible-asset-allocation.md) | momentum-cs | validated | Keller & van Putten (2012), SSRN 2193735 | 2026-07-14 |
| [Commodity Momentum with Intra-Market Correlation Filter](ideas/commodity-momentum-correlation-filter.md) | momentum-cs | rejected | Fuertes, Miffre & Rallis (2010), Journal of Banking & Finance 34(10) | 2026-07-14 |
| [Defensive Asset Allocation (Breadth Momentum + Canary)](ideas/defensive-asset-allocation-canary.md) | regime | validated | Keller & Keuning (2018), SSRN 3212862 | 2026-07-14 |
| [Gold–Silver Ratio Mean Reversion](ideas/gold-silver-ratio-mean-reversion.md) | mean-reversion | validated | Escribano & Granger (1998), Journal of Forecasting 17(2) | 2026-07-14 |
| [Vigilant Asset Allocation (VAA)](ideas/vigilant-asset-allocation.md) | regime | rejected | Keller & Keuning (2017), SSRN 3002624 | 2026-07-14 |
| [Short-Term (1-Month) Reversal](ideas/short-term-reversal.md) | mean-reversion | validated | Jegadeesh (1990), Journal of Finance 45(3) | 2026-07-14 |
| [Minimum Semivariance Portfolio](ideas/minimum-semivariance.md) | diversification | validated | Estrada (2008), Journal of Applied Finance 18(1) | 2026-07-14 |
| [Minimum CVaR Portfolio](ideas/minimum-cvar.md) | diversification | validated | Rockafellar & Uryasev (2000), Journal of Risk 2(3) | 2026-07-14 |
| [Hierarchical Equal Risk Contribution (HERC)](ideas/hierarchical-equal-risk-contribution.md) | diversification | rejected | Raffinot (2018), SSRN 3237540 | 2026-07-14 |
