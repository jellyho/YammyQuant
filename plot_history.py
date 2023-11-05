import pandas as pd
from plotly.subplots import make_subplots
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

history = pd.read_csv('history/history.csv', index_col=False).fillna(0)        # history를 불러와서 Nan을 전부 0으로 채우는 과정이다.
ticker = list(set(history['ticker']).remove(0))        # 실제 거래 기록이 있는 ticker들만 추출한다.
data = None        # data = {ticker_1 : dataFrame_1, ticker_2 : dataFrame_2...}        # backtesting 때 사용할 불러올 실제 SQL dataFrame을 dictionary 형태로 ticker별로 정리한다.

data_1 = {}        # ticker별로 Open, Volume, sign(Volume)을 데이터 프레임 형태로 저장한다. 주가 그래프와 거래량을 그리는 용도이다.
for name in ticker:
    _open = data[name]['open']
    _volume = data[name]['volume']
    _sign = np.sign(data[name]['open']-data[name]['close'])
    _frame = pd.DataFrame({'open' : _open,
                           'volume' : _volume,
                           'sign' : _sign})
    data_1[name] = _frame

data_2 = {}        # BUY 기록의 quantity, 거래액, 거래직전 meanPrice, 거래직후 meanPrice를 저장한다.
for name in ticker:
    _history_2 = history[history['type'] != 'sell' & history['ticker'] == (name or 0)]        # sell이 아니고 ticker가 현재 ticker이고 0인 것만 뽑는다. 0을 뽑는 것은 meanPrice기록이 필요해서이다.
    _frame = pd.DataFrame(columns=['time','quantity','tradeCash','meanNow','meanPre'])
    for _ in range(len(_history_2[0])):
        if _history_2['type'][_] == 'buy':        # type이 0이면 거래 기록이 아닌 지갑 기록이기 때문이다.
            row = {'time' : _history_2['time'][_],
                   'quantity' : _history_2['quantity'][_],
                   'tradeCash' : _history_2['quantity'][_] * _history_2['tradePrice'][_],
                   'meanNow' : _history_2[f'{name}_meanPrice'][_+1],        # 거래 기록 바로 다음 행이 그 거래가 반영된 지갑 기록이다.
                   'meanPre' : _history_2[f'{name}_meanPrice'][_-1]}        # 거래 기록 바로 전 행이 그 거래가 반영되기 전의 지갑 기록이다.
            _frame = pd.concat([_frame,row],ignore_index=True)
    data_2[name] = _frame

data_3 = {}        # Sell 기록의 quantity, 거래액, 그시점 meanPrice와 tradePrice
for name in ticker:
    _history_3 = history[history['type'] != 'buy' & history['ticker'] == (name or 0)]
    _frame = pd.DataFrame(columns=['time','quantity','tradeCash','percentage','benefit','meanPrice','open'])
    _data = data[name]
    for _ in range(len(_history_3[0])):
        if _history_3['type'][_] == 'sell':
            row = {'time' : _history_3['time'][_],
                   'quantity' : _history_3['quantity'][_],
                   'tradeCash' : _history_3['quantity'][_]*_history_3['tradePrice'][_],
                   'percentage' : _history_3['percentage'][_],
                   'benefit' : _history_3['benefit'][_],
                   'meanPrice' : _history_3[f'{name}_meanPrice'][_-1],
                   'tradePrice' : _history_3['tradePrice'][_]
            }
        _frame = pd.concat([_frame,row],ignore_index=True)
    data_3[name] = _frame

data_4 = {}        # subgraph에 표시되어야 할 보조지표이다.
for name in ticker:
    _data_sub = data[name].drop(['open','high','low','close','volume'] + [i for i in data.columns if 'ma' in i],axis='columns')
    data_4[name] = _data_sub

data_5 = {}        # seed, cash, tickerCash 만 추출한다.
for name in ticker:
    _history = history[history.ticker == 0]        # 거래 기록 행을 전부 제거한다.
    _data_cash = [_history.ticker.isna()][['time', 'seed'] + [i for i in _history.columns if 'cash' in i]]
    data_5[name] = _data_cash

data_6 = {}        # ma, ema와 같이 main graph에 같이 그려질 보조지표를 추출한다.
for name in ticker:
    _data_main = data[name].drop([i for i in data.columns if 'ma' not in i] - ['time'],axis='columns')
    data_6[name] = _data_main

data_7 = {}        # 얇은 세로 표시선을 그리기 위한 용도이다.
for name in ticker:
    _history = history[history.ticker != 0]        # 지갑 기록 행을 전부 제거한다.
    _data_line = history[history.ticker == name & history.type == ('buy' or 'sell')]['time','ticker']
    data_7[name] = _data_line


