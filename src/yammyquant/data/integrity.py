"""Candle data-integrity checks — the unglamorous layer that keeps backtests honest.

Bad candles (duplicate timestamps, missing bars, NaNs, impossible OHLC) silently
corrupt indicators and inflate or destroy backtest results. :func:`candle_integrity`
audits a series and returns a structured report; the operator surfaces it via
``yq integrity`` and a roll-up in ``yq doctor``.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from yammyquant.data.candle import Candle


def candle_integrity(candle: Candle, interval_seconds: Optional[float] = None) -> dict:
    """Audit a candle series for structural and value problems.

    Parameters
    ----------
    candle:
        The series to check.
    interval_seconds:
        Expected spacing between bars, in seconds. When given, gaps (missing
        bars) are detected against it; when ``None`` gap detection is skipped.

    Returns a dict of issue counts plus an overall ``ok`` flag.
    """
    idx = pd.DatetimeIndex(candle.index)
    n = len(idx)
    out = {
        "bars": n, "duplicates": 0, "out_of_order": 0, "gaps": 0,
        "missing_estimate": 0, "nan_rows": 0, "bad_ohlc": 0,
        "nonpositive": 0, "ok": True,
    }
    if n == 0:
        return out

    # -- timestamp structure (unit-agnostic: seconds via Timedelta) -------
    out["duplicates"] = int(idx.duplicated().sum())
    deltas = np.asarray((idx[1:] - idx[:-1]).total_seconds()) if n > 1 else np.array([])
    out["out_of_order"] = int((deltas <= 0).sum())  # zero/negative => unsorted/dup
    if interval_seconds and deltas.size:
        exp = float(interval_seconds)
        forward = deltas[deltas > 0]
        gap_mask = forward > 1.5 * exp
        out["gaps"] = int(gap_mask.sum())
        if gap_mask.any():
            out["missing_estimate"] = int(np.round(forward[gap_mask] / exp - 1).sum())

    # -- value sanity (OHLC) ----------------------------------------------
    o, h, l, c = (candle.open.astype(float), candle.high.astype(float),
                  candle.low.astype(float), candle.close.astype(float))
    stack = np.vstack([o, h, l, c])
    nan_row = np.isnan(stack).any(axis=0)
    out["nan_rows"] = int(nan_row.sum())
    finite = ~nan_row
    out["nonpositive"] = int((finite & (stack <= 0).any(axis=0)).sum())
    bad = finite & ((h < l) | (h < o) | (h < c) | (l > o) | (l > c))
    out["bad_ohlc"] = int(bad.sum())

    out["ok"] = not (out["duplicates"] or out["out_of_order"] or out["gaps"]
                     or out["nan_rows"] or out["bad_ohlc"] or out["nonpositive"])
    return out
