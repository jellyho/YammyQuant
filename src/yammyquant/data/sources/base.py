"""DataSource protocol — the common interface for reading candles."""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from yammyquant.data.candle import Candle


@runtime_checkable
class DataSource(Protocol):
    """Anything that can produce a :class:`Candle` for a ticker/interval/range."""

    def read(
        self,
        ticker: str,
        interval: str,
        start: Optional[datetime | str] = None,
        end: Optional[datetime | str] = None,
    ) -> Candle:
        ...
