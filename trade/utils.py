from enum import Enum


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
        self.__data = {}
        self.__data['time'] = time
        self.__data['action'] = action
        self.__data['ticker'] = ticker
        self.__data['price'] = price
        self.__data['quantity'] = quantity
        self.filled = False
        self.allowed_keywords = ['time', 'action', 'ticker', 'price', 'quantity', 'quoteQty', 'fee', 'ID']

    def fill(self, **kwargs):
        for kw in kwargs.keys():
            if kw in self.allowed_keywords:
                self.__data[kw] = kwargs[kw]
            else:
                KeyError("Invalid Keywords for Order")
        self.filled = True

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
            self.__orders.append(order)

    def __str__(self):
        s = "History\n"
        for o in self.__orders:
            s += str(o)
            s += "\n"
        return s