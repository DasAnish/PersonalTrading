"""Tests for analytics/blend.py — preferred-strategy weighted blend."""

import json
from pathlib import Path

import pytest

from analytics import blend as blend_mod


def _write_weights(results_dir: Path, key: str, weights: dict) -> None:
    d = results_dir / "strategies" / key
    d.mkdir(parents=True, exist_ok=True)
    rows = [{**weights, "date": "2026-06-30T00:00:00"}]
    (d / "weights_history.json").write_text(json.dumps(rows), encoding="utf-8")


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "blend.json"
    saved = blend_mod.save_blend({"a": 0.4, "b": 0.6}, path=path)
    assert saved == {"a": 0.4, "b": 0.6}
    assert blend_mod.load_blend(path) == {"a": 0.4, "b": 0.6}


def test_save_drops_nonpositive_and_rejects_empty(tmp_path):
    path = tmp_path / "blend.json"
    saved = blend_mod.save_blend({"a": 0.5, "b": 0.0, "c": -1}, path=path)
    assert saved == {"a": 0.5}
    with pytest.raises(ValueError):
        blend_mod.save_blend({"x": 0.0}, path=path)


def test_load_missing_returns_empty(tmp_path):
    assert blend_mod.load_blend(tmp_path / "nope.json") == {}


def test_blended_target_weights_normalized(tmp_path):
    _write_weights(tmp_path, "s1", {"AAA": 0.5, "BBB": 0.5})
    _write_weights(tmp_path, "s2", {"BBB": 1.0})
    # 0.5*s1 + 0.5*s2 = AAA 0.25, BBB 0.75 -> already sums to 1.
    out = blend_mod.blended_target_weights({"s1": 0.5, "s2": 0.5}, results_dir=tmp_path)
    assert abs(out["AAA"] - 0.25) < 1e-9
    assert abs(out["BBB"] - 0.75) < 1e-9
    assert abs(sum(out.values()) - 1.0) < 1e-9


def test_blended_skips_missing_strategy(tmp_path):
    _write_weights(tmp_path, "s1", {"AAA": 1.0})
    out = blend_mod.blended_target_weights(
        {"s1": 0.5, "ghost": 0.5}, results_dir=tmp_path
    )
    # ghost has no saved weights -> skipped; result is just s1, normalized.
    assert out == {"AAA": 1.0}


def test_blended_empty_blend(tmp_path):
    assert blend_mod.blended_target_weights({}, results_dir=tmp_path) == {}


def test_close_price_base_scaling(tmp_path):
    """close_price_base applies pence->pounds scale and manual overrides."""
    import pandas as pd

    from data import cache as cache_mod

    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    # A pence-quoted ETF at 5000 (=£50) and a GBP-quoted one at 100.
    for sym, close in (("EQQQ", 5000.0), ("VUSA", 100.0)):
        pd.DataFrame({"close": [close]}).to_parquet(
            cache_dir / f"{sym}_20200101_20260101.parquet"
        )
    units = {
        "scale_to_base": {"EQQQ": 0.01, "LPLA": 0.8},
        "manual_close": {"LPLA": 250.0},
    }
    assert cache_mod.close_price_base("EQQQ", units, cache_dir=str(cache_dir)) == 50.0
    assert cache_mod.close_price_base("VUSA", units, cache_dir=str(cache_dir)) == 100.0
    # LPLA has no cache file -> manual_close 250 USD * 0.8 FX = 200 GBP.
    assert cache_mod.close_price_base("LPLA", units, cache_dir=str(cache_dir)) == 200.0
    # Unknown symbol, no data -> None.
    assert cache_mod.close_price_base("ZZZ", units, cache_dir=str(cache_dir)) is None
