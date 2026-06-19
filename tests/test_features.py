import numpy as np
import pandas as pd

from yammyquant.data.candle import Candle
from yammyquant.data.features import compute_features, latest_features, FeatureStore


def _candle(n=120):
    idx = pd.date_range("2023-01-01", periods=n, freq="1D")
    close = 100 + 10 * np.sin(np.arange(n) / 8.0)
    df = pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close,
         "volume": np.linspace(1000, 2000, n)},
        index=idx,
    )
    return Candle("BTCUSDT", df, interval="1d")


def test_compute_features_columns_and_alignment():
    feats = compute_features(_candle())
    for col in ["return_1", "log_return", "realized_vol_20", "volume_z_20",
                "rsi_14", "trend_ratio", "atr_pct"]:
        assert col in feats.columns
    assert len(feats) == 120


def test_latest_features_is_json_safe():
    latest = latest_features(_candle())
    # all values are float or None (NaN -> None)
    assert all(v is None or isinstance(v, float) for v in latest.values())


def test_feature_store_roundtrip(tmp_path):
    fs = FeatureStore(tmp_path / "feat")
    feats = compute_features(_candle())
    fs.write("BTCUSDT", "1d", feats)
    back = fs.read("BTCUSDT", "1d")
    assert list(back.columns) == list(feats.columns)
    assert len(back) == len(feats)
