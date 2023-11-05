import pandas as pd
from plotly.subplots import make_subplots
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# 아래에서 부터 데이터 정제 다시 해야 할듯 사실상 기록이 코인하나당 csv파일 하나이기 때문에 위의 방식은 복잡할뿐더러 의미가 없다.

class drawGraph:
    def __init__(self, history, data, indicator_dict):       # history : 히스토리, candle_list = [Candle.data, Candle.사용한 보조지표 들]
        self.history = history
        self.data = data
        self.indicator_df = pd.DataFrame() # for문 까지가 보조지표만을 모아둔 데이터 프레임을 만드는 과정이다.
        self.indicator_df.index = self.data.index
        for _ in range(len(indicator_dict)):
            key = list(indicator_dict.keys())[_]
            self.indicator_df[key] = indicator_dict[key]
        self.candle_df = pd.concat([data,self.indicator_df],axis = 1)

    def filtering(self):
        self.candle_df['vSign'] = np.sign(self.candle_df['open']-self.candle_df['close'])
        self.history['tradeCash'] = round(self.history['tradePrice'] * self.history['quantity'],4)
        self.history['preMean'] = self.history['ticker_meanPrice'].shift(1)
        self.history['preNow'] = self.history['ticker_meanPrice'].shift(-1)

        self.sub_indi = self.candle_df.drop([ _ for _ in self.candle_df.columns if ('ma' in _) or ('ema' in _)]+['open','high','low','close','volume','vSign'],axis=1)
        self.main_indi = self.candle_df.drop(self.sub_indi.columns,axis=1)
        self.trade = self.history.dropna(subset = ['type'])
        self.trade.set_index(keys='time')
        self.cash = self.history.dropna(subset = ['seed'])
        self.cash.set_index(keys='time')

        self.sub_indi.to_csv('plot_data/sub_indi.csv')
        self.main_indi.to_csv('plot_data/main_indi.csv')
        self.cash.to_csv('plot_data/cash.csv')
        self.trade.to_csv('plot_data/trade.csv')

