"""Local candle store backed by DuckDB + Parquet.

Replaces the old MySQL ``SQLUpdater`` / ``SQLReader`` with a zero-config,
file-based store. Each ``(ticker, interval)`` pair is one Parquet file under
the store directory; DuckDB queries them directly, so range reads stay fast
even with millions of rows and no server to run.

Parameterized queries are used throughout (no f-string SQL injection).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import duckdb
import pandas as pd

from yammyquant.data.candle import Candle, OHLCV_COLUMNS


def _to_datetime(value: Optional[datetime | str]) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


class DuckDBStore:
    """A directory of Parquet candle files queried via DuckDB.

    Parameters
    ----------
    path:
        Directory that holds the Parquet files (created if missing).
    """

    def __init__(self, path: str | Path = "data_store"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    # -- layout ------------------------------------------------------------
    def _file(self, ticker: str, interval: str) -> Path:
        return self.path / f"{ticker}_{interval}.parquet"

    def info(self) -> Dict[str, List[str]]:
        """Map of ticker -> list of available intervals on disk."""
        out: Dict[str, List[str]] = {}
        for f in sorted(self.path.glob("*.parquet")):
            ticker, _, interval = f.stem.rpartition("_")
            out.setdefault(ticker, []).append(interval)
        return out

    # -- write -------------------------------------------------------------
    def write(self, candle: Candle) -> None:
        """Insert/upsert candle data, deduplicating on the timestamp index."""
        if candle.interval is None:
            raise ValueError("Candle.interval is required to store data.")
        new = candle.data.copy()
        new.index.name = "date"
        file = self._file(candle.ticker, candle.interval)
        if file.exists():
            existing = pd.read_parquet(file)
            combined = pd.concat([existing, new])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
        else:
            combined = new.sort_index()
        combined.to_parquet(file)

    def last_time(self, ticker: str, interval: str) -> Optional[datetime]:
        """Timestamp of the most recent stored bar, or ``None`` if empty."""
        file = self._file(ticker, interval)
        if not file.exists():
            return None
        con = duckdb.connect()
        try:
            row = con.execute(
                "SELECT max(date) FROM read_parquet(?)", [str(file)]
            ).fetchone()
        finally:
            con.close()
        return row[0] if row else None

    # -- read --------------------------------------------------------------
    def read(
        self,
        ticker: str,
        interval: str,
        start: Optional[datetime | str] = None,
        end: Optional[datetime | str] = None,
    ) -> Candle:
        file = self._file(ticker, interval)
        if not file.exists():
            raise FileNotFoundError(f"No stored data for {ticker} {interval} ({file}).")

        start, end = _to_datetime(start), _to_datetime(end)
        query = "SELECT date, open, high, low, close, volume FROM read_parquet(?)"
        params: list = [str(file)]
        clauses = []
        if start is not None:
            clauses.append("date >= ?")
            params.append(start)
        if end is not None:
            clauses.append("date <= ?")
            params.append(end)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY date"

        con = duckdb.connect()
        try:
            df = con.execute(query, params).fetch_df()
        finally:
            con.close()
        df = df.set_index("date")
        return Candle(ticker, df[list(OHLCV_COLUMNS)], interval=interval)
