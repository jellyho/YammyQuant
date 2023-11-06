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
        self.allowed_keywords = ['time', 'action', 'ticker', 'price', 'quantity', 'fill', 'fee', 'ID']

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

# /// deprecated ///
# class History:
#     def __init__(self):
#         self.allowed_keywords = ['action', 'ticker', 'price', 'quantity', 'quoteQty', 'fee', 'ID', 'Yield']
#         self.__orders = pd.DataFrame(columns=self.allowed_keywords)

#     def add(self, order):
#         if type(order) is not Order:
#             raise TypeError
#         else:
#             self.__orders.loc[order['time']] = pd.Series(order.data)

#     def show(self, ignore_hold=True):
#         s = "History\n"
#         s += str(self.__orders[self.__orders['action'] != Action.HOLD] if ignore_hold else self.__orders)
#         print(s)

class Portfolio:
    def __init__(self, seed, fee, ticker=[]):         # seed : 초기 시드, fee : 수수료, ticker : 내가 거래할 종목을 미리 알려준다. 혹여나 없어도 크게 상관은 없지만 최대한 있게 하자.
        self.fee = fee
        self.wallet = {'cash' : seed}        # type : {'cash' : int, ticker_1 : [quan,mPrice], ticker_2 : [quan,mPrice]} 근데 일단 우린 그냥 하나의 종목에만 씁시다.
        for i in ticker:
            self.wallet[i] = [0, 0]
        self.history = pd.DataFrame(columns=['time', 'ticker', 'type', 'tradePrice', 'quantity', 'percentage', 'benefit', 'seed', 'cash'])

    # def update_trade(self, time, type_, price, quantity, ticker):        # 거래 주문을 받을 때 마다 지갑을 최신화 하는 함수.
    def update_trade(self, order):
        if order.filled and order['action'] != Action.HOLD:
            if order['action'] == Action.BUY:
                updateCash = order['price'] * order['quantity'] * (1 + self.fee)        # 매수 할 때 차감 될 금액이다.
                if self.wallet['cash'] >= updateCash:        # 현금이 충분한지 확인한다.
                    if order['ticker'] in self.wallet:        # 거래 내역이 존재하는 종목인 경우이다.
                        _quantity, _price = self.wallet[order['ticker']]
                        self.wallet['cash'] -= updateCash        # 현금 차감
                        self.wallet[order['ticker']][0] += order['quantity']        # 수량 추가
                        self.wallet[order['ticker']][1] = self._get_meanPrice(_quantity, _price, order['quantity'], order['price'])        # 평균 매수가 수정
                        self._record(order['time'], order['ticker'], order['action'], order['price'], order['quantity'], 0, 0)        # 매수는 수익 구조가 없으니 returnRate와 return을 0으로 지정한다.
                    else:        # 거래 내역이 없는 종목이다.
                        self.wallet['cash'] -= updateCash
                        self.wallet[order['ticker']] = [order['quantity'], order['price']]        # 새롭게 종목 기록 생성 
                        self._record(order['time'], order['ticker'], order['action'], order['price'], order['quantity'], 0, 0)
                        self.history.insert(len(self.history.columns),f"{order['ticker']}_cash",None)
                        self.history.insert(len(self.history.columns),f"{order['ticker']}_quantity",None)
                        self.history.insert(len(self.history.columns),f"{order['ticker']}_meanPrice",None)
                else:        # 현금이 부족한 경우이다.
                    print("not enough cash to buy")
            elif order['action'] == Action.SELL:
                if order['ticker'] in self.wallet:
                    if self.wallet[order['ticker']][0] >= order['quantity']:
                        self.wallet[order['ticker']][0] -= order['quantity']
                        self.wallet['cash'] += order['price'] * order['quantity'] * (1-self.fee)
                        per, tot = self._cal_margin(order['price'], self.wallet[order['ticker']][1], order['quantity'])        # 이번 거래로 얼마의 수익이 났는지를 기존 평균 매수가를 사용해서 구한다.
                        self._record(order['time'], order['ticker'], order['action'], order['price'], order['quantity'], per, tot)
                        if self.wallet[order['ticker']][0] == 0:
                            self.wallet[order['ticker']][1] = 0        # 보유량이 0개이면 평균 매수가도 0으로 다시 바꾼다.
                    else:
                        print("not enough coin to sell")
                else:
                    self.wallet[order['ticker']] = [0, 0]        # 새롭게 종목 기록 생성
                    self.history.insert(len(self.history.columns),f"{order['ticker']}_cash",None)
                    self.history.insert(len(self.history.columns),f"{order['ticker']}_quantity",None)
                    self.history.insert(len(self.history.columns),f"{order['ticker']}_meanPrice",None)
                    print("you don't have this coin")
        
        self.update_seed({order['ticker'] : order['price']}, order['time'])
  
    def _get_meanPrice(self, q1, p1, q2, p2):        # 매수 평균가를 계산해주는 함수이다.
        newPrice = round((q1 * p1 + p2 * q2) / (q1 + q2), 2)
        return newPrice
  
    def _cal_margin(self, tradePrice, meanPrice, quantity):
        percentage = round((tradePrice - meanPrice) / meanPrice - self.fee * (tradePrice / meanPrice), 3)        # 매수 평균가와 현재 가격 사이의 퍼센트에 수수료를 뺀 수치
        size = percentage * meanPrice * quantity        # percentage에 평균 매수가와 거래량을 곱해서 총 수익을 반환한다
        return percentage*100, size

    def update_seed(self, currentPrice, time):        # dictionary = 우리가 다루는 코인들의 가장 최근 Open 가격을 dict 형태로 보유한 겁니다. 매번 거래 판단이 실시할 때 마다 시행하세요!!!
        row = {'time' : time}
        row['cash'] = self.wallet['cash']
        seed = 0
        for ticker in self.wallet:
            if ticker != 'cash':
                seed += self.wallet[ticker][0] * currentPrice[ticker]
                row[f'{ticker}_meanPrice'] = self.wallet[ticker][1]        # cash의 경우 int형이고 나머지 종목의 경우 [quantity,meanPrice] 형태인걸 주의합시다!
                row[f'{ticker}_quantity'] = self.wallet[ticker][0]
                row[f'{ticker}_cash'] = self.wallet[ticker][0] * currentPrice[ticker]
            else :
                seed += self.wallet['cash']        # 기존 거래 내역이 없던 종목의 경우 다른 종목과 시간대를 맞춰주기 위해서 판단 로직이 수행된 횟수 만큼 0을 앞에 집어넣는다.
        row['seed'] = seed

        row_df = pd.DataFrame(row,index=[0])
        self.history = pd.concat([self.history,row_df],ignore_index=True)


    def _record(self, time, ticker, type_, tradePrice, quantity, percentage, benefit):        # Dataframe에 거래 기록을 추가하는 함수이다. 자동으로 수행된다.
        row = {'time' : pd.DatetimeIndex([time]), 'ticker' : ticker, 'type' : type_, 'tradePrice' : tradePrice, 'quantity' : quantity, 'percentage' : percentage, 'benefit' : benefit}
        row_df = pd.DataFrame(row,index=[0])
        self.history = pd.concat([self.history,row_df],ignore_index=True)
        

    def save_history(self):
        time_start = self.history['time'].tolist()[0]
        time_end = self.history['time'].tolist()[-1]
        self.history.to_csv(f'history/{time_start}_{time_end}.csv',index=False)        # 요거 저장하는 건데 맞게 돌아갈지를 모르겠다. 확인부탁