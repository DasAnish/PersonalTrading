# Project Structure

This document describes every file and directory in the PersonalTrading project.

> **Excluded from this listing:** `results/` (generated backtest output), `data/cache/` (parquet market data cache), `__pycache__/`, `.git/`, `references/` (external research repos), and `ib_wrapper.egg-info/` (build artefacts).

---

## Root

| Path | Description |
|------|-------------|
| `CLAUDE.md` | Development guidelines for Claude Code: no automated orders, GSD planning rules, code standards |
| `README.md` | Project overview and quick-start instructions |
| `LICENSE` | Software licence |
| `pyproject.toml` | Python package config, dependencies, and tool settings (Black, mypy, pytest) |
| `.env` | Local IB Gateway credentials (not committed) |
| `.env.example` | Template showing required env vars |
| `.gitignore` | Files excluded from version control |
| `.mcp.json` | MCP server registration so Claude Code can use the `ib-trading` tools |
| `backtest_trend_vs_hrp.log` | Legacy log file from an early manual backtest run |
| `test_example_symbol.py` | Scratch test script for symbol lookup |
| `test_positions.py` | Scratch test script for live position monitoring |

---

## `analytics/`

Analytics utilities used by the backtesting engine to compute and visualise performance.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `metrics.py` | Sharpe, Sortino, Calmar, VaR/CVaR, max drawdown, rolling metrics |
| `overfitting.py` | DSR (Deflated Sharpe Ratio), PBO (Probability of Backtest Overfitting), k-fold temporal stability analysis |
| `visualizations.py` | Matplotlib chart helpers (equity curve, drawdown, weights) |

---

## `backtesting/`

Core simulation engine that replays monthly rebalancing decisions against historical prices.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `engine.py` | `BacktestEngine` — orchestrates the backtest loop: fetches data, calls strategy, records transactions |
| `portfolio_state.py` | `PortfolioState` — tracks current holdings, cash, and portfolio value at each step |
| `transaction.py` | `Transaction` data model representing a single buy/sell |

---

## `config/`

| File | Description |
|------|-------------|
| `default_config.yaml` | Default runtime config: IB connection settings, backtest parameters, result paths |

---

## `data/`

Market data management. All reads go through `MarketDataService` which either fetches from IB or serves from the local parquet cache.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `cache.py` | `HistoricalDataCache` — reads/writes parquet files under `data/cache/` |
| `market_data_service.py` | `MarketDataService` singleton — IB Gateway first, parquet fallback |
| `preprocessing.py` | Data cleaning helpers: forward-fill, align dates, adjust for splits |
| `cache/` | Parquet files with historical OHLCV data (not in version control) |

---

## `decisions/`

Architecture decision records written during development sessions.

| File | Description |
|------|-------------|
| `strategy_architecture_2026-03-13.md` | Decision: unified `Strategy` ABC with `AssetStrategy`, `AllocationStrategy`, and `OverlayStrategy` subtypes |

---

## `docs/`

Project documentation.

| File | Description |
|------|-------------|
| `cli.md` | CLI reference for all four `run_backtest.py` modes and `run_optimization.py` |
| `dashboard.md` | Dashboard usage guide: pages, API endpoints, URL patterns |
| `project.md` | Project overview: components, IB connection setup, backtesting spec |
| `project-structure.md` | This file — annotated directory listing |
| `session_log.md` | Running session log: next actions and known bugs |
| `strategies.md` | Strategy architecture, algorithms, and composability guide |

---

## `examples/`

Standalone scripts demonstrating how to use the IB wrapper directly.

| File | Description |
|------|-------------|
| `basic_connection.py` | Connect to IB Gateway and check account summary |
| `fetch_historical_data.py` | Fetch and display historical bars for a given symbol |
| `monitor_positions.py` | Stream live position updates from IB |
| `portfolio_realtime.py` | Poll and print portfolio value in real time |

---

## `ib_wrapper/`

Async wrapper around `ib_insync` that exposes a clean interface for the rest of the project.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker; re-exports `IBClient` |
| `client.py` | `IBClient` — main async client: connects, fetches data, queries portfolio |
| `config.py` | `IBConfig` dataclass loaded from `.env` (host, port, client ID) |
| `connection.py` | Low-level connection management and reconnect logic |
| `exceptions.py` | Custom exceptions: `IBConnectionError`, `IBDataError`, etc. |
| `market_data.py` | Methods for requesting historical and live market data from IB |
| `models.py` | Data classes: `Bar`, `Position`, `AccountSummary` |
| `portfolio.py` | Methods for reading positions and account values |
| `utils.py` | Helpers: contract builders, date formatters |

---

## `logs/`

| File | Description |
|------|-------------|
| `.gitkeep` | Keeps the empty directory in version control |
| `ib_wrapper.log` | Runtime log from the IB wrapper (rotated, not committed) |

---

## `mcp_server/`

[MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that exposes project tools to Claude Code.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `server.py` | FastMCP server with 7 tools: `get_account_summary`, `get_positions`, `get_historical_data`, `get_multiple_historical_data`, `get_backtest_results`, `list_strategies`, `run_backtest` |

---

## `optimization/`

Parameter search and walk-forward validation for strategy tuning.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `param_sweep.py` | Grid search over strategy parameter space; runs a full backtest per combination |
| `walk_forward.py` | Walk-forward analysis: trains on a window, tests on the next, rolls forward |

---

## `plan/`

Active GSD (Get Stuff Done) plan files. Managed by `/clearplan`, `/continueplan`, and `/newplan` skills.

| File | Description |
|------|-------------|
| `index.md` | Master index: all phases and their statuses |
| `state.md` | Current phase, current TODO, and progress counts |
| `phase-NN-<slug>.md` | Per-phase files with TODOs and notes |

---

## `scripts/`

Entry-point scripts invoked from the command line.

| File | Description |
|------|-------------|
| `run_backtest.py` | Main backtest runner — four modes: `--all`, `--strategy`, `--compare`, `--optimize` |
| `run_optimization.py` | Parameter sweep and walk-forward runner |
| `run_overfitting.py` | Overfitting analysis CLI — runs DSR, PBO, k-fold for a single strategy |
| `run_all_overfitting.py` | Batch overfitting analysis across all 80+ strategy definitions |
| `add_strategy_tags.py` | Tag management tool for strategy metadata |
| `run_hrp_backtest.py` | Legacy single-strategy HRP backtest script |
| `test_hrp_backtest.py` | Legacy manual test for HRP output |
| `serve_results.py` | Thin entry point — imports `server.app.create_app()` and starts Flask on port 5000 |
| `start_dashboard.sh` | Shell helper to activate venv and start the dashboard |
| `start_dashboard.bat` | Windows batch helper equivalent |

### `scripts/server/`

Flask dashboard server, split into focused modules.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `app.py` | `create_app()` factory — creates the Flask app and registers blueprints |
| `data.py` | Data loading: `load_strategies_index`, `load_strategy_data`, per-series helpers; caches the index in memory |
| `api.py` | API blueprint — all JSON endpoints: `/api/strategies`, `/api/strategies/summary`, `/api/strategy/<key>`, monthly returns, rolling metrics, CSV export, multi-strategy comparison |
| `routes.py` | Page blueprint — `/` overview page (sortable table of all strategies) and `/strategy/<key>` detail page (7-tab Chart.js dashboard); both auto-refresh every 10 seconds |

---

## `strategies/`

Strategy implementations. All strategies implement `get_weights(context) → dict[str, float]`.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker; re-exports core types |
| `core.py` | ABC hierarchy: `Strategy`, `AssetStrategy`, `AllocationStrategy`, `OverlayStrategy`, `StrategyContext` |
| `base.py` | Compatibility aliases re-exporting from `core.py` |
| `equal_weight.py` | `EqualWeightStrategy` — 1/N allocation |
| `hrp.py` | `HRPStrategy` — Hierarchical Risk Parity using scipy clustering |
| `minimum_variance.py` | `MinimumVarianceStrategy` — scipy.optimize.minimize on portfolio variance |
| `momentum.py` | `MomentumStrategy` — top-N by trailing return |
| `dual_momentum.py` | `DualMomentumStrategy` — absolute + relative momentum |
| `mean_reversion.py` | `MeanReversionStrategy` — z-score based allocation |
| `adaptive_asset_allocation.py` | `AdaptiveAssetAllocationStrategy` — momentum + min-var hybrid |
| `protective_asset_allocation.py` | `ProtectiveAssetAllocationStrategy` — defensive/protective allocation |
| `volatility_momentum.py` | `VolatilityMomentumStrategy` — volatility-adjusted momentum |
| `skewness_weighted.py` | `SkewnessWeightedStrategy` — penalises negative skew |
| `trend_signal_mvo.py` | `TrendSignalMVOStrategy` — trend signals into mean-variance optimisation |
| `trend_signal_rp.py` | `TrendSignalRPStrategy` — trend signals into risk parity |
| `meta_portfolio.py` | `MetaPortfolioStrategy` — combines multiple strategies as sub-strategies |
| `overlays.py` | `VolatilityTargetStrategy`, `ConstraintStrategy`, `LeverageStrategy` — weight transformations applied after allocation |
| `risk_parity.py` | `RiskParityStrategy` — inverse-volatility weighting |
| `trend_following.py` | `TrendFollowingStrategy` — EWMA momentum with signal half-life |
| `models.py` | `StrategyInfo`, `ParameterDefinition` metadata models |
| `strategy_loader.py` | `StrategyLoader` — recursively builds `Strategy` objects from JSON definition files |

---

## `strategy_definitions/`

Declarative JSON strategy definitions. The loader in `strategies/strategy_loader.py` reads these files and assembles the corresponding Python objects.

| Path | Description |
|------|-------------|
| `README.md` | Guide to writing and composing strategy definitions |
| `CUSTOM_STRATEGIES.md` | Notes on adding new custom strategies |
| `assets/` | Individual instrument definitions (VUSA, SSLN, SGLN, IWRD, EQQQ, BRNT, CRUD, COMM, COMML, AIGC, IIND, IMEU, WCOA, VUTY) — 14 UK ETFs |
| `allocations/` | Weight-calculation strategies (HRP, trend following, equal weight, momentum, risk parity, minimum variance) |
| `overlays/` | Weight-transformation overlays (volatility targets at 12/15/30%, box constraints) |
| `composed/` | Multi-layer strategies — an allocation wrapped in one or more overlays |
| `portfolios/` | Meta-portfolios that combine multiple composed strategies |
| `markets/` | Market universe definitions (currently empty / placeholder) |

---

## `tests/`

Pytest test suite.

| File | Description |
|------|-------------|
| `__init__.py` | Package marker |
| `conftest.py` | Shared fixtures: in-memory data, mock IB client, test strategy definitions |
| `test_backtest_e2e.py` | End-to-end backtest tests: run full backtest and assert output shape |
| `test_connection.py` | IB connection tests (skipped if IB Gateway not running) |
| `test_core_architecture.py` | Unit tests for the strategy ABC hierarchy and `StrategyContext` |
| `test_market_data.py` | Tests for `MarketDataService` and `HistoricalDataCache` |
| `test_optimization.py` | Tests for `param_sweep` and `walk_forward` (12 tests) |
| `test_overfitting.py` | Tests for DSR, PBO, and k-fold overfitting analysis (49 tests) |
| `test_portfolio.py` | Tests for `PortfolioState` accounting |
| `test_strategies.py` | Unit tests for each strategy implementation |

---

## `ai_iterations/`

Session summaries written by Claude at the end of significant development sessions. Useful for understanding what changed and why.

| File | Description |
|------|-------------|
| `2026-03-12_original_plan.md` | Initial project plan and scope |
| `2026-03-13_completion_summary.md` | Summary of session completing the backtest pipeline |
| `2026-03-13_strategy_architecture_refactor.md` | Notes on the strategy ABC refactor |

---

## `.claude/`

Claude Code configuration for this project.

| Path | Description |
|------|-------------|
| `settings.json` | Shared Claude Code settings (auto-approved commands, permissions) |
| `settings.local.json` | Local overrides (not committed) |
| `commands/build-strategies.md` | `/build-strategies` command — research and build new strategies using a 4-agent pipeline |
| `commands/clearplan.md` | `/clearplan` command — reset and scaffold the GSD plan |
| `commands/continueplan.md` | `/continueplan` command — resume the active plan |
| `commands/newplan.md` | `/newplan` command — create and immediately begin a new plan |
| `skills/backtest/SKILL.md` | `/backtest` skill — run a single named strategy backtest |
| `skills/backtest-all/SKILL.md` | `/backtest-all` skill — run all strategy definitions |
| `skills/build-strategies/SKILL.md` | `/build-strategies` skill (team variant, requires agent teams env var) |
| `skills/build-strategies-auto/SKILL.md` | `/build-strategies-auto` skill — unattended strategy builder loop |
| `skills/dashboard/SKILL.md` | `/dashboard` skill — start the Flask dashboard |
| `skills/optimize/SKILL.md` | `/optimize` skill — run parameter sweep on a strategy |
| `skills/rebalance/SKILL.md` | `/rebalance` skill — generate a rebalance report (no orders sent) |
