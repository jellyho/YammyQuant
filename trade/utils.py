from enum import Enum
import pandas as pd


class Action(Enum):
    HOLD = 'HOLD'
    BUY = 'BUY'
    SELL = 'SELL'
    LONG = 'LONG'
    CLOSE_LONG = 'CLOSE_LONG'
    SHORT = 'SHORT'
    CLOSE_SHORT = 'CLOSE_SHORT'


class Order:
    def __init__(self, time=None, action=None, ticker=None, price=None, quantity=None):
        self.data = {}
        self.data['time'] = time
        self.data['action'] = action
        self.data['ticker'] = ticker
        self.data['price'] = price
        self.data['quantity'] = quantity
        self.filled = False
        self.allowed_keywords = ['time', 'action', 'ticker', 'price', 'quantity', 'quoteQty', 'fee', 'ID', 'Yield']

    def fill(self, **kwargs):
        for kw in kwargs.keys():
            if kw in self.allowed_keywords:
                self.data[kw] = kwargs[kw]
            else:
                KeyError("Invalid Keywords for Order")
        self.filled = True

    def __str__(self):
        return f"Order : {self.data}"

    def __getitem__(self, index):
        if index not in self.data.keys():
            raise IndexError
        else:
            return self.data[index]


class History:
    def __init__(self):
        self.allowed_keywords = ['action', 'ticker', 'price', 'quantity', 'quoteQty', 'fee', 'ID', 'Yield']
        self.__orders = pd.DataFrame(columns=self.allowed_keywords)

    def add(self, order):
        if type(order) is not Order:
            raise TypeError
        else:
            self.__orders.loc[order['time']] = pd.Series(order.data)

    def show(self, ignore_hold=True):
        s = "History\n"
        s += str(self.__orders[self.__orders['action'] != Action.HOLD] if ignore_hold else self.__orders)
        print(s)
