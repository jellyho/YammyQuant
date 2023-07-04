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
        maf = obs.ma(self.first)
        mas = obs.ma(self.second)

        if maf[-1] > mas[-1] and maf[-2] < mas[-2]:
            return [Order(time=obs.index[-1], action=a.BUY, price=obs[-1].Close)]
        elif maf[-1] < mas[-1] and maf[-2] > mas[-2]:
            return [Order(time=obs.index[-1], action=a.SELL, price=obs[-1].Close)]
        else:
            return [Order(time=obs.index[-1], action=a.HOLD)]
