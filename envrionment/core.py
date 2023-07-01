import pandas as pd
pd.options.mode.chained_assignment = None


class Environment:
    def __init__(self):
        self.reset()

    def getTradeFee(self):  #
        return 0

    def getTaxRate(self):  #
        return 0

    def getData(self):  #
        self.ObserveLength = 50
        return None

    def reset(self):
        self.trade_fee = self.get_trade_fee()
        self.tax_rate = self.get_tax_rate()
        self.Data = self.get_Data()
        self.idx = self.ObserveLength - 2

    def observable(self):
        return (len(self.Data) - 1 > self.idx)

    def observe(self):
        if self.Observable():
            self.idx = self.idx + 1
            return TimeSeries(df=self.Data[(self.idx - self.ObserveLength + 1):(self.idx + 1)])