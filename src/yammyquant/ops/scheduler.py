"""A minimal scheduler so the platform keeps working between operator sessions.

Runs :func:`yammyquant.ops.operator.run_cycle` on a fixed interval — refreshing
watchlist data, scanning for signals, marking positions, and notifying when
something needs attention. No external dependency; for production you can also
drive ``yq cycle`` from system cron instead of holding this loop open.
"""

from __future__ import annotations

import time
from typing import Optional

from yammyquant.state.store import LiveState
from yammyquant.data.sources.store import DuckDBStore
from yammyquant.ops import operator as ops


def run_loop(
    state_path: str = "yammyquant_state.db",
    store_path: str = "data_store",
    interval_seconds: int = 300,
    exchange: Optional[str] = None,
    max_cycles: Optional[int] = None,
    sleep=time.sleep,
) -> int:
    """Run cycles until ``max_cycles`` (or forever). Returns cycles completed."""
    state = LiveState(state_path)
    store = DuckDBStore(store_path)
    state.log("schedule", f"scheduler started (every {interval_seconds}s)")
    n = 0
    while max_cycles is None or n < max_cycles:
        try:
            ops.run_cycle(store, state, exchange=exchange)
        except Exception as exc:  # never let one bad cycle kill the loop
            state.log("schedule", f"cycle error: {exc}")
        n += 1
        if max_cycles is not None and n >= max_cycles:
            break
        sleep(interval_seconds)
    return n
