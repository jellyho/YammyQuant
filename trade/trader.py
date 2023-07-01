class Trader:
    def __init__(self):
        self._Env = None
        self._Agent = None

    def set_Env(self, env):
        self._Env = env

    def set_Agent(self, agent):
        self._agent = agent

    def method_Buy(self, TI):  #
        return TI

    def method_Sell(self, TI):  #
        return TI

    def method_Long(self, TI):  #
        return TI

    def method_Short(self, TI):  #
        return TI

    def trade(self):
        while self.Env.Observable():
            data = self.Env.Observe()
            acts = self.Agent.act(data)
            for act in acts:
                t = TradeInfo()
                t.append(act.Time, act.Action, act.Code, act.Amount, act.Price, act.Fee)
                self.ActDict[act.Action](t)
            self.Portfolio.update(data)

    def Buy(self, ti):
        ti = self.method_Buy(ti)
        ti = self.Portfolio.add(ti)
        self.TradeHistory.append(ti)
        return None

    def Sell(self, ti):
        ti = self.method_Sell(ti)
        ti = self.Portfolio.add(ti)
        self.TradeHistory.append(ti)
        return None

    def Long(self, ti):
        ti = self.method_Long(ti)
        ti = self.Portfolio.add(ti)
        self.TradeHistory.append(ti)
        return None

    def Close_Long(self, ti):
        ti = self.method_Long(ti)
        ti = self.Portfolio.add(ti)
        self.TradeHistory.append(ti)
        return None

    def Short(self, ti):
        ti = self.method_Short(ti)
        ti = self.Portfolio.add(ti)
        self.TradeHistory.append(ti)
        return None

    def Close_Short(self, ti):
        ti = self.method_Short(ti)
        ti = self.Portfolio.add(ti)
        self.TradeHistory.append(ti)
        return None