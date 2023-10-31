from trade.utils import Action, Portfolio

class Agent:
    def act(self, observation):
        raise NotImplementedError


class Trader:
    def __init__(self, env=None, agent=None, portfolio=None):
        pass

    def setEnv(self, env):
        self._env = env

    def setAgent(self, agent):
        self._agent = agent

    def setPortfolio(self, portfolio):
        self.portfolio = portfolio

    def _trade_method(self, order):
        """
        :param order: Order Class instance
        :return: filled order if trade go well, False if trade not happen.
        """
        return True

    def trade(self):
        self._env.reset()
        while self._env.observable():
            data = self._env.observe()
            acts = self._agent.act(data)
            for act in acts:
                result = self._trade_method(act)
                if result is not None:
                    self.portfolio.update_trade(act)
