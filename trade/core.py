from trade.utils import History, Action


class Agent:
    def act(self, observation):
        raise NotImplementedError


class Trader:
    def __init__(self, env=None, agent=None):
        self._env = env
        self._agent = agent
        self.history = History()

    def setEnv(self, env):
        self._env = env

    def setAgent(self, agent):
        self._agent = agent

    def _trade_method(self, order):
        """
        :param order: Order Class instance
        :return: True if trade go well, False if trade not happen.
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
                    self.history.add(act)
