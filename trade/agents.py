from trade.core import Agent
from trade.utils import Action as a
from trade.utils import Order
import pandas as pd
import datetime

class MACrossAgent(Agent):
    """
    MACross Implementation
    """
    def __init__(self, first=5, second=20):
        self.first = first
        self.second = second

    def act(self, obs):
        maf = obs.SMA(self.first)
        mas = obs.SMA(self.second)

        if maf[-1] > mas[-1] and maf[-2] < mas[-2]:
            return [Order(time=obs.index[-1], action=a.BUY, ticker=obs.ticker, price=obs[-1].close, quantity=1.0000)]
        elif maf[-1] < mas[-1] and maf[-2] > mas[-2]:
            return [Order(time=obs.index[-1], action=a.SELL, ticker=obs.ticker, price=obs[-1].close, quantity=1.0000)]
        else:
            return [Order(time=obs.index[-1], action=a.HOLD, ticker=obs.ticker, price=obs[-1].close)] # pass current price even in HOLD Action... to update seed


class VotalityBreakoutAgent(Agent):
    """
    VotalityBreakout Implementation
    """
    def __init__(self, k=0.5):
        self.k = k

    def act(self, obs):
        ran = obs.high[-2] - obs.low[-2]
        if obs.high[-1] > obs.close[-2] + ran * self.k:
                return [Order(time=obs.index[-1], action=a.BUY, ticker=obs.ticker, price=obs.close[-2] + ran * self.k, quantity=1.0000)
                        ,Order(time=obs.index[-1], action=a.SELL, ticker=obs.ticker, price=obs[-1].close, quantity=1.0000)]
        else:
            return [Order(time=obs.index[-1], action=a.HOLD, ticker=obs.ticker, price=obs[-1].close)]