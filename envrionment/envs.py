from data.readers import BinanceReader
from data.core import Candle
from envrionment.core import Environment


class SimpleBacktestingEnvironment(Environment):
    def __init__(self, reader):
        self.reader = reader
        super(SimpleBacktestingEnvironment, self).__init__()

    def getData(self):
        return self.reader.read()

