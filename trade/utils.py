import pandas as pd
pd.options.mode.chained_assignment = None
from enum import Enum

class Action(Enum):
    HOLD = 0
    BUY = 1
    SELL = 2
    LONG = 3
    CLOSE_LONG = 4
    SHORT = 5
    CLOSE_SHORT = 6

class Order:
    def __init__(self, time=None, action=None, ticker=None, amount=None, price=None):
        self.__data = {}
        self.__data['time'] = time
        self.__data['action'] = action
        self.__data['ticker'] = ticker
        self.__data['amount'] = amount
        self.__data['price'] = price

    def __str__(self):
        return f"Order : {self.__data}"

    def __getitem__(self, index):
        if index not in self.__data.keys():
            raise IndexError
        else:
            return self.__data[index]


class History:
    def __init__(self):
        self.__orders = []

    def add(self, order):
        if type(order) is not Order:
            raise TypeError
        else:
            self.__orders.append(Order)

    def __str__(self):
        s = "History\n"
        for o in self.__orders:
            s += str(o)
            s += "\n"
        return s