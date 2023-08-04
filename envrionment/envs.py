from data.readers import BinanceReader
from data.core import Candle
from envrionment.core import Environment
import os
from binance.client import Client


class SimpleBacktestingEnvironment(Environment):
    def __init__(self, reader):
        self.reader = reader
        super(SimpleBacktestingEnvironment, self).__init__()

    def getData(self):
        return self.reader.read()


class BinanceEnvironment(Environment):
    def __init__(self):
        self.reader = BinanceReader()
        super(BinanceEnvironment, self).__init__()

    def getTradeFee(self):
        return self.client.get_trade_fee()



