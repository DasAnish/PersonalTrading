# Phase 2 — Update StrategyLoader for JSON

## Goal
Update `strategies/strategy_loader.py` to load `.json` strategy definition files using the new nested format (replacing the YAML `market:` + `layers:` style).

## New JSON schema vs old YAML schema
| Concept | YAML | JSON |
|---------|------|------|
| Asset universe | `market: uk_etfs` (ref to market file) | `"underlying": ["assets/vusa", ...]` (list of asset refs) |
| Allocation | `type: allocation`, `market: uk_etfs` | `type: "allocation"`, `underlying: [...]` |
| Composed | `type: composed`, `layers: [overlay1, overlay2]` | `type: "composed"`, `class: OverlayClass`, `underlying: {...inline allocation...}` |
| Asset def | N/A | `type: "asset"`, `class: AssetStrategy`, `parameters: {symbol, currency, exchange}` |

## TODOs
- [x] Update `_find_strategy_file` to look for `.json` first, then `.yaml` as fallback; handle path-based refs like `"assets/vusa"` (maps to `strategy_definitions/assets/vusa.json`)
- [x] Replace `_load_yaml` with `_load_file` that handles both `.json` (via `json.load`) and `.yaml` (via `yaml.safe_load`)
- [x] Add `_build_strategy_from_def(definition: dict)` — recursive builder:
  - `type: "asset"` → instantiate `AssetStrategy(**parameters)`
  - `type: "allocation"` → build underlying list from file refs OR legacy `market:` key, then instantiate AllocationStrategy
  - `type: "composed"` → recursively build `underlying` (inline dict), then instantiate overlay class
  - `type: "market"` → legacy YAML path, instantiate market class (e.g. `UKETFsMarket()`)
- [x] Update `build_strategy(key)` to use `_build_strategy_from_def`
- [x] Update `list_strategies(type)` to scan `*.json` files (and `*.yaml` as fallback), deduplicating by stem name
- [x] Verify loading works for all existing JSON files: `equal_weight`, `hrp_single`, `hrp_15vol`, `hrp_30vol`, `trend_15vol`, `trend_30vol`

## Notes
