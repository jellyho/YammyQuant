from utils import History

class Agent:
    def act(self, observation):
        raise NotImplementedError

class Trader:
    def __init__(self):
        self._env = None
        self._agent = None
        self._history = History

    def setEnv(self, env):
        self._env = env

    def setAgent(self, agent):
        self._agent = agent

    def _trade_method(self, order):
        """
        :param order: Order Class instance
        :return: True if trade go well, False if trade not happen.
        """
        raise NotImplementedError

    def trade(self):
        while self._env.Observable():
            data = self._env.Observe()
            acts = self._agent.act(data)
            for act in acts:
                result = self._trade_method(act)
                if result is not None:
                    self._history.add(act)