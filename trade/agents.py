from trade.core import Agent
from trade.utils import Action as a
from trade.utils import Order


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
