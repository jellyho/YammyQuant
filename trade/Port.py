import pandas as pd
import datetime
from trade.core import Action as a

class Portfolio:
    def __init__(self, seed, fee, ticker=[]):         # seed : 초기 시드, fee : 수수료, ticker : 내가 거래할 종목을 미리 알려준다. 혹여나 없어도 크게 상관은 없지만 최대한 있게 하자.
        self.fee = fee
        self.wallet = {'cash' : seed}        # type : {'cash' : int, ticker_1 : [quan,mPrice], ticker_2 : [quan,mPrice]} 근데 일단 우린 그냥 하나의 종목에만 씁시다.
        for i in ticker:
            self.wallet[i] = [0, 0]
        self.history = pd.DataFrame(columns=['time', 'ticker', 'type', 'tradePrice', 'quantity', 'percentage', 'benefit', 'seed', 'cash'])

    def update_trade(self, time, type_, price, quantity, ticker):        # 거래 주문을 받을 때 마다 지갑을 최신화 하는 함수.
        if type_ == 'buy':
            updateCash = price * quantity * (1 + self.fee)        # 매수 할 때 차감 될 금액이다.
            if self.wallet['cash'] >= updateCash:        # 현금이 충분한지 확인한다.
                if ticker in self.wallet:        # 거래 내역이 존재하는 종목인 경우이다.
                    _quantity, _price = self.wallet[ticker]
                    self.wallet['cash'] -= updateCash        # 현금 차감
                    self.wallet[ticker][0] += quantity        # 수량 추가
                    self.wallet[ticker][1] = self._get_meanPrice(_quantity, _price, quantity, price)        # 평균 매수가 수정
                    self._record(time, ticker, type_, price, quantity, 0, 0)        # 매수는 수익 구조가 없으니 returnRate와 return을 0으로 지정한다.
                else:        # 거래 내역이 없는 종목이다.
                    self.wallet['cash'] -= updateCash
                    self.wallet[ticker] = [quantity, price]        # 새롭게 종목 기록 생성 
                    self._record(time, ticker, type_, price, quantity, 0, 0)
                    self.history.insert(len(self.history.columns),f'{ticker}_cash',None)
                    self.history.insert(len(self.history.columns),f'{ticker}_quantity',None)
                    self.history.insert(len(self.history.columns),f'{ticker}_meanPrice',None)
            else:        # 현금이 부족한 경우이다.
                print("not enough cash to buy")
        elif type_ == 'sell':
            if ticker in self.wallet:
                if self.wallet[ticker][0] >= quantity:
                    self.wallet[ticker][0] -= quantity
                    self.wallet['cash'] += price * quantity * (1-self.fee)
                    per, tot = self._cal_margin(price, self.wallet[ticker][1], quantity)        # 이번 거래로 얼마의 수익이 났는지를 기존 평균 매수가를 사용해서 구한다.
                    self._record(time, ticker, type_, price, quantity, per, tot)
                    if self.wallet[ticker][0] == 0:
                        self.wallet[ticker][1] = 0        # 보유량이 0개이면 평균 매수가도 0으로 다시 바꾼다.
                else:
                    print("not enough coin to sell")
            else:
                self.wallet[ticker] = [0, 0]        # 새롭게 종목 기록 생성
                self.history.insert(len(self.history.columns),f'{ticker}_cash',None)
                self.history.insert(len(self.history.columns),f'{ticker}_quantity',None)
                self.history.insert(len(self.history.columns),f'{ticker}_meanPrice',None)
                print("you don't have this coin")
  
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


if __name__ == "__main__":
    price_1d = {'BTC' : 100, 'ETH' : 50, 'XRP' : 5}
    price_2d = {'BTC' : 120, 'ETH' : 40, 'XRP' : 10}
    price_3d = {'BTC' : 140, 'ETH' : 30, 'XRP' : 5}
    price_4d = {'BTC' : 160, 'ETH' : 20, 'XRP' : 10}
    price_5d = {'BTC' : 180, 'ETH' : 10, 'XRP' : 5}
    price_6d = {'BTC' : 200, 'ETH' : 5, 'XRP' : 15}

    fake_market = Portfolio(10000,0.004,)
    print(fake_market.wallet,'\n')        # 초기 상태의 지갑 확인

    fake_market.update_trade('2023-01-02 00:00:00','buy',100,20,'BTC')        # 구매 확인 및 지갑에 티커 추가 확인
    fake_market.update_seed(price_1d,'2023-01-02 00:00:00')
    print(fake_market.wallet,'\n')

    fake_market.update_seed(price_2d,'2023-01-02 10:00:00')        # 가격 변동에 따른 자산 변동 반영 확인
    print(fake_market.wallet,'\n')

    fake_market.update_trade('2023-01-03 00:00:00','buy',140,20,'BTC')        # 추가 구매 후 평균가 수정 확인
    fake_market.update_trade('2023-01-04 00:00:00','buy',30,10,'ETH')        # 동시간대에 다른 종목 구매
    fake_market.update_seed(price_3d,'2023-01-04 00:00:00')
    print(fake_market.wallet,'\n')

    fake_market.update_trade('2023-01-05 00:00:00','sell',10,100,'XRP')        # 존재하지 않는 티커 판매
    fake_market.update_trade('2023-01-06 00:00:00','buy',10000,1000,'BTC')        # 재산을 넘어서는 티커 구매
    fake_market.update_seed(price_4d,'2023-01-06 00:00:00')
    print(fake_market.wallet,'\n')

    fake_market.update_trade('2023-01-07 00:00:00','sell',10000,1000,'ETH')        # 재산을 넘어서는 티커 판매
    fake_market.update_trade('2023-01-08 00:00:00','sell',180,30,'BTC')        # 적정량의 보유 티커 판매
    fake_market.update_seed(price_5d,'2023-01-08 00:00:00')
    print(fake_market.wallet,'\n')

    fake_market.update_trade('2023-01-09 00:00:00','sell',5,10,'ETH')        # 전부 판매하면 매수 평균가 다시 0으로 전환
    fake_market.update_seed(price_6d,'2023-01-09 00:00:00')
    print(fake_market.wallet,'\n')

    print(fake_market.history)

    print(type(fake_market.history.time[0]), fake_market.history.time[0] + datetime.timedelta(1)) # time column의 데이터 타입