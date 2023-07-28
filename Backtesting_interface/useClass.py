import talib
import numpy as np

class Indicator :
    def __init__(self,data) :
        self.data = data
    def ma(self,n) :
        return talib.SMA(self.data['Close'],timeperiod=n)
    def rsi(self,n) :
        return talib.RSI(self.data['Close'],timeperiod=n)
    def bol(self,n) :
        return talib.BBANDS(self.data['Close'],timeperiod=n)
    def cal_earn(self,list_,start) :
        buy=0
        asset = start
        mode = 0 #미보유, 1은 보유
        accum = []
        short = []
        price = self.data['Close'].to_list()

        for _ in range(list_) :
            if list_[_] == 1 :
                buy = price[_-1]
                accum.append(asset*(1+(price[_]-buy)/buy))
                short.append((price[_]/buy-1)*100)
                mode = 1
            elif list_[_] == -1 :
                buy = 0
                accum.append(asset*(1+(price[_-1]-buy)/buy))
                asset = asset*(1+(price[_-1]-buy)/buy)
                short.append(0)
                mode = 0
            else :
                if mode == 0 :
                    accum.append(asset)
                    short.append(0)
                else :
                    accum.append(asset*(1+(price[_]-buy)/buy))
                    short.append((price[_]/buy-1)*100)
        
        return accum, short
