class Environment:
    def __init__(self):
        self.observeRange = 50
        self.tradeFee = 0.004
        self.taxRate = 0
        self.data = None
        self.idx = 0

    def getTradeFee(self):  #
        return 0

    def getTaxRate(self):  #
        return 0

    def getData(self):  #
        raise NotImplementedError

    def reset(self):
        self.tradeFee = self.getTradeFee()
        self.taxRate = self.getTaxRate()
        self.data = self.getData()
        self.idx = self.observeRange - 2

    def observable(self):
        return len(self.data) - 1 > self.idx

    def observe(self):
        if self.observable():
            self.idx = self.idx + 1
            return self.data[(self.idx - self.observeRange + 1):(self.idx + 1)]
