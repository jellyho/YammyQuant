"""Combine multiple strategies / signals into one decision.

Two layers share the same vote-aggregation core (:func:`aggregate_votes`):

* :class:`Ensemble` — a :class:`Strategy` that blends several sub-strategies and
  is itself backtestable / optimizable.
* the operator's ``decide`` — mixes the enabled strategies' live signals per
  watchlist symbol using the same rules.

A *vote* is each member's action on the current bar: ``"BUY"`` (+1), ``"SELL"``
(-1) or ``"HOLD"`` (0). Rules turn the (optionally weighted) votes into a final
buy/sell decision:

* ``any``       — buy if any member buys (and none sells); the permissive default.
* ``weighted``  — net weighted score must clear ``±threshold`` (in [-1, 1]).
* ``majority``  — the leading side must be ≥ ``threshold`` of the members voting.
* ``unanimous`` — all members that voted must agree (no opposing vote).
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from yammyquant.data.candle import Candle
from yammyquant.backtest.order import Action, Order
from yammyquant.strategy.base import Strategy

RULES = ("any", "weighted", "majority", "unanimous")


def aggregate_votes(
    votes: Sequence[str],
    weights: Optional[Sequence[float]] = None,
    rule: str = "weighted",
    threshold: float = 0.5,
) -> dict:
    """Blend per-member votes into ``{"buy", "sell", "score"}``.

    ``votes`` are ``"BUY"`` / ``"SELL"`` / ``"HOLD"`` (anything else counts as
    HOLD). ``score`` is the net weighted vote in [-1, 1] regardless of rule.
    """
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}; choose from {RULES}")
    n = len(votes)
    weights = list(weights) if weights is not None else [1.0] * n
    if len(weights) != n:
        raise ValueError("weights length must match votes length")

    buy_w = sum(w for v, w in zip(votes, weights) if v == "BUY")
    sell_w = sum(w for v, w in zip(votes, weights) if v == "SELL")
    total_w = sum(abs(w) for w in weights) or 1.0
    buy_n = sum(1 for v in votes if v == "BUY")
    sell_n = sum(1 for v in votes if v == "SELL")
    score = round((buy_w - sell_w) / total_w, 4)

    if rule == "any":
        buy, sell = buy_w > 0, sell_w > 0
    elif rule == "unanimous":
        buy, sell = (buy_n > 0 and sell_n == 0), (sell_n > 0 and buy_n == 0)
    elif rule == "majority":
        active = buy_n + sell_n
        frac = (max(buy_n, sell_n) / active) if active else 0.0
        buy = buy_n > sell_n and frac >= threshold
        sell = sell_n > buy_n and frac >= threshold
    else:  # weighted
        buy, sell = score >= threshold, score <= -threshold
    return {"buy": bool(buy), "sell": bool(sell), "score": score}


class Ensemble(Strategy):
    """Blend several strategies into one via a voting rule.

    Each member sees a window sized to its own ``warmup``; the ensemble warms up
    to the largest member so every voter always has enough history.
    """

    def __init__(self, members: Sequence[Strategy], weights: Optional[Sequence[float]] = None,
                 rule: str = "weighted", threshold: float = 0.5, size: float = 1.0):
        if not members:
            raise ValueError("ensemble needs at least one member strategy")
        self.members = list(members)
        self.weights = list(weights) if weights is not None else [1.0] * len(self.members)
        if len(self.weights) != len(self.members):
            raise ValueError("weights length must match members")
        if rule not in RULES:
            raise ValueError(f"unknown rule {rule!r}; choose from {RULES}")
        self.rule, self.threshold, self.size = rule, threshold, size
        self.warmup = max(m.warmup for m in self.members)
        self._stance = ["HOLD"] * len(self.members)
        self._side = "FLAT"

    def reset(self) -> None:
        for m in self.members:
            m.reset()
        self._stance = ["HOLD"] * len(self.members)
        self._side = "FLAT"

    def on_bar(self, window: Candle) -> List[Order]:
        # Members signal on crossover *bars* only; carry each member's last
        # directional signal forward as a persistent stance so the vote reflects
        # who is currently long/short — otherwise members rarely agree on the
        # same bar and weighted/majority rules almost never fire.
        for i, m in enumerate(self.members):
            if len(window) < m.warmup:
                continue
            orders = m.on_bar(window[-m.warmup:])
            if orders:
                self._stance[i] = orders[0].action.value
        agg = aggregate_votes(self._stance, self.weights, self.rule, self.threshold)
        price, time = float(window.close[-1]), window.index[-1]
        # Debounce: trade only when the aggregate stance flips (long ↔ flat).
        if agg["buy"] and not agg["sell"] and self._side != "LONG":
            self._side = "LONG"
            return [Order(Action.BUY, window.ticker, self.size, price, time)]
        if agg["sell"] and not agg["buy"] and self._side == "LONG":
            self._side = "FLAT"
            return [Order(Action.SELL, window.ticker, self.size, price, time)]
        return []
