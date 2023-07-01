from core import Agent
from utils import Action as a
from utils import Order


class VolatilityBreakoutAgent(Agent):
    """
    VolatilityBreakout by Larry Williams
    """
    def __init__(self, k):
        self.k = k

    def act(self, observation):
        return Order()