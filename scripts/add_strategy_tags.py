"""One-off script to add 'tags' field to all strategy definition JSON files."""

import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "strategy_definitions"

# fmt: off
TAGS: dict[str, list[str]] = {
    # --- composed ---
    "composed/aaa_full_universe_15vol":         ["aaa", "momentum", "min-variance", "full-universe", "vol-15"],
    "composed/aaa_full_universe_30vol":         ["aaa", "momentum", "min-variance", "full-universe", "vol-30"],
    "composed/aaa_top2_15vol":                  ["aaa", "momentum", "min-variance", "core-4", "vol-15", "concentrated"],
    "composed/aaa_top2_30vol":                  ["aaa", "momentum", "min-variance", "core-4", "vol-30", "concentrated"],
    "composed/aaa_top3_15vol":                  ["aaa", "momentum", "min-variance", "core-4", "vol-15"],
    "composed/aaa_top3_30vol":                  ["aaa", "momentum", "min-variance", "core-4", "vol-30"],
    "composed/dual_momentum_15vol":             ["dual-momentum", "momentum", "trend-filter", "core-4", "vol-15"],
    "composed/dual_momentum_30vol":             ["dual-momentum", "momentum", "trend-filter", "core-4", "vol-30"],
    "composed/dual_momentum_full_universe_15vol": ["dual-momentum", "momentum", "trend-filter", "full-universe", "vol-15"],
    "composed/dual_momentum_full_universe_30vol": ["dual-momentum", "momentum", "trend-filter", "full-universe", "vol-30"],
    "composed/dual_momentum_invested_15vol":    ["dual-momentum", "momentum", "trend-filter", "core-4", "vol-15", "fully-invested"],
    "composed/equal_weight_15vol":              ["equal-weight", "core-4", "vol-15", "benchmark"],
    "composed/hrp_15vol":                       ["hrp", "core-4", "vol-15", "risk-managed"],
    "composed/hrp_30vol":                       ["hrp", "core-4", "vol-30", "risk-managed"],
    "composed/hrp_average_15vol":               ["hrp", "core-4", "vol-15", "risk-managed"],
    "composed/hrp_commodity_theme_15vol":       ["hrp", "commodity", "vol-15", "risk-managed", "inflation-hedge"],
    "composed/hrp_commodity_theme_30vol":       ["hrp", "commodity", "vol-30", "risk-managed", "inflation-hedge"],
    "composed/hrp_full_universe_15vol":         ["hrp", "full-universe", "vol-15", "risk-managed"],
    "composed/hrp_full_universe_30vol":         ["hrp", "full-universe", "vol-30", "risk-managed"],
    "composed/hrp_growth_theme_15vol":          ["hrp", "growth", "vol-15", "risk-managed"],
    "composed/hrp_growth_theme_30vol":          ["hrp", "growth", "vol-30", "risk-managed"],
    "composed/hrp_with_constraints":            ["hrp", "core-4", "constrained"],
    "composed/mean_reversion_15vol":            ["mean-reversion", "contrarian", "core-4", "vol-15"],
    "composed/mean_reversion_30vol":            ["mean-reversion", "contrarian", "core-4", "vol-30"],
    "composed/mean_reversion_full_universe_15vol": ["mean-reversion", "contrarian", "full-universe", "vol-15"],
    "composed/mean_reversion_full_universe_30vol": ["mean-reversion", "contrarian", "full-universe", "vol-30"],
    "composed/min_var_15vol":                   ["min-variance", "core-4", "vol-15", "risk-managed"],
    "composed/min_var_30vol":                   ["min-variance", "core-4", "vol-30", "risk-managed"],
    "composed/min_var_full_universe_15vol":     ["min-variance", "full-universe", "vol-15", "risk-managed"],
    "composed/min_var_full_universe_30vol":     ["min-variance", "full-universe", "vol-30", "risk-managed"],
    "composed/min_var_with_constraints":        ["min-variance", "core-4", "constrained"],
    "composed/momentum_commodity_top2_15vol":   ["momentum", "commodity", "vol-15", "concentrated"],
    "composed/momentum_commodity_top2_30vol":   ["momentum", "commodity", "vol-30", "concentrated"],
    "composed/momentum_top1_15vol":             ["momentum", "core-4", "vol-15", "concentrated"],
    "composed/momentum_top1_30vol":             ["momentum", "core-4", "vol-30", "concentrated"],
    "composed/momentum_top2_15vol":             ["momentum", "core-4", "vol-15"],
    "composed/momentum_top2_1m_15vol":          ["momentum", "core-4", "vol-15", "short-lookback"],
    "composed/momentum_top2_3m_15vol":          ["momentum", "core-4", "vol-15", "short-lookback"],
    "composed/momentum_top2_6m_15vol":          ["momentum", "core-4", "vol-15"],
    "composed/momentum_top2_6m_30vol":          ["momentum", "core-4", "vol-30"],
    "composed/momentum_top2_30vol":             ["momentum", "core-4", "vol-30"],
    "composed/momentum_top2_with_constraints":  ["momentum", "core-4", "constrained"],
    "composed/momentum_top3_15vol":             ["momentum", "core-4", "vol-15"],
    "composed/momentum_top3_30vol":             ["momentum", "core-4", "vol-30"],
    "composed/momentum_top3_full_universe_15vol": ["momentum", "full-universe", "vol-15"],
    "composed/protective_asset_allocation_15vol": ["paa", "core-4", "vol-15", "defensive", "trend-filter"],
    "composed/risk_parity_15vol":               ["risk-parity", "core-4", "vol-15", "risk-managed"],
    "composed/risk_parity_30vol":               ["risk-parity", "core-4", "vol-30", "risk-managed"],
    "composed/risk_parity_full_universe_15vol": ["risk-parity", "full-universe", "vol-15", "risk-managed"],
    "composed/risk_parity_full_universe_30vol": ["risk-parity", "full-universe", "vol-30", "risk-managed"],
    "composed/risk_parity_with_constraints":    ["risk-parity", "core-4", "constrained"],
    "composed/skewness_weighted_15vol":         ["skewness", "core-4", "vol-15"],
    "composed/skewness_weighted_30vol":         ["skewness", "core-4", "vol-30"],
    "composed/trend_15vol":                     ["trend-following", "core-4", "vol-15"],
    "composed/trend_30vol":                     ["trend-following", "core-4", "vol-30"],
    "composed/trend_constrained_vol_target":    ["trend-following", "core-4", "constrained", "conservative"],
    "composed/trend_following_full_universe_15vol": ["trend-following", "full-universe", "vol-15"],
    "composed/trend_following_full_universe_30vol": ["trend-following", "full-universe", "vol-30"],
    "composed/trend_signal_mvo_15vol":          ["trend-signal", "mvo", "core-4", "vol-15"],
    "composed/trend_signal_mvo_conservative_15vol": ["trend-signal", "mvo", "core-4", "vol-15", "conservative"],
    "composed/trend_signal_rp_15vol":           ["trend-signal", "risk-parity", "core-4", "vol-15"],
    "composed/trend_signal_rp_30vol":           ["trend-signal", "risk-parity", "core-4", "vol-30"],
    "composed/trend_with_vol_12":               ["trend-following", "core-4", "conservative"],

    # --- portfolios ---
    "portfolios/meta_aaa_ensemble_15vol":       ["ensemble", "aaa", "momentum", "vol-15"],
    "portfolios/meta_aaa_momentum_30vol":       ["ensemble", "aaa", "momentum", "vol-30"],
    "portfolios/meta_all_season":               ["ensemble", "all-weather", "risk-managed"],
    "portfolios/meta_balanced_all_weather":     ["ensemble", "all-weather", "contrarian", "risk-managed"],
    "portfolios/meta_commodity_suite":          ["ensemble", "commodity", "inflation-hedge"],
    "portfolios/meta_commodity_trend_skew":     ["ensemble", "commodity", "trend-following", "skewness"],
    "portfolios/meta_conservative_core_15vol":  ["ensemble", "vol-15", "conservative", "risk-managed"],
    "portfolios/meta_contrarian":               ["ensemble", "contrarian", "mean-reversion"],
    "portfolios/meta_contrarian_suite":         ["ensemble", "contrarian", "mean-reversion"],
    "portfolios/meta_defensive_core":           ["ensemble", "defensive", "risk-managed", "conservative"],
    "portfolios/meta_full_universe_diversified": ["ensemble", "full-universe", "diversified"],
    "portfolios/meta_full_universe_ensemble":   ["ensemble", "full-universe", "diversified"],
    "portfolios/meta_full_universe_ensemble_15vol": ["ensemble", "full-universe", "vol-15", "diversified"],
    "portfolios/meta_grand_ensemble":           ["ensemble", "diversified", "all-weather"],
    "portfolios/meta_growth_commodity_blend":   ["ensemble", "growth", "commodity", "diversified"],
    "portfolios/meta_high_sharpe":              ["ensemble", "diversified"],
    "portfolios/meta_high_sharpe_session":      ["ensemble", "momentum", "aaa", "mean-reversion", "trend-following"],
    "portfolios/meta_mean_reversion_suite":     ["ensemble", "mean-reversion", "contrarian"],
    "portfolios/meta_momentum_contrarian_blend": ["ensemble", "momentum", "contrarian"],
    "portfolios/meta_momentum_ensemble":        ["ensemble", "momentum"],
    "portfolios/meta_momentum_multi_horizon":   ["ensemble", "momentum", "multi-lookback"],
    "portfolios/meta_momentum_multi_lookback_15vol": ["ensemble", "momentum", "multi-lookback", "vol-15"],
    "portfolios/meta_multi_volatility":         ["ensemble", "hrp", "trend-following", "diversified"],
    "portfolios/meta_risk_managed":             ["ensemble", "risk-managed", "diversified"],
    "portfolios/meta_tactical_diversification": ["ensemble", "diversified", "tactical"],
    "portfolios/meta_theme_diversified":        ["ensemble", "growth", "commodity", "hrp", "diversified"],
    "portfolios/meta_trend_aaa_blend_15vol":    ["ensemble", "trend-following", "aaa", "vol-15"],
    "portfolios/meta_trend_hrp_15vol":          ["ensemble", "trend-following", "hrp", "vol-15"],
    "portfolios/meta_trend_hrp_30vol":          ["ensemble", "trend-following", "hrp", "vol-30"],
    "portfolios/meta_trend_signal_suite":       ["ensemble", "trend-signal", "mvo", "risk-parity"],
    "portfolios/meta_trend_skew":               ["ensemble", "trend-following", "skewness"],
    "portfolios/meta_trend_skew_mvo":           ["ensemble", "trend-following", "skewness", "mvo"],
    "portfolios/meta_ultimate":                 ["ensemble", "diversified", "all-weather"],
    "portfolios/meta_ultimate_30vol":           ["ensemble", "diversified", "vol-30"],
}
# fmt: on


def main() -> None:
    updated = 0
    skipped = 0

    for key, tags in TAGS.items():
        path = BASE / f"{key}.json"
        if not path.exists():
            print(f"  SKIP (not found): {key}")
            skipped += 1
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("tags") == tags:
            skipped += 1
            continue

        data["tags"] = tags

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")

        print(f"  TAGGED: {key}  ->  {tags}")
        updated += 1

    print(f"\nDone. {updated} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
