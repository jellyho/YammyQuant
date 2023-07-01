class Environment:
    def __init__(self):
        self.observeRange = 50
        self.tradeFee = 0
        self.taxRate = 0
        self.data = None
        self.idx = 0
        self.reset()

    def getTradeFee(self):  #
        return 0

    def getTaxRate(self):  #
        return 0

    def getData(self):  #
        return None

    def reset(self):
        self.tradeFee = self.getTradeFee()
        self.taxRate = self.getTaxRate()
        self.data = self.getData()
        self.idx = self.observeRange - 2

    def observable(self):
        return (len(self.Data) - 1 > self.idx)

    def observe(self):
        if self.Observable():
            self.idx = self.idx + 1
            return TimeSeries(df=self.Data[(self.idx - self.ObserveLength + 1):(self.idx + 1)])