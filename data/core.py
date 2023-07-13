import pandas as pd
import numpy as np
import pymysql

intervalList = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '1w', '1M']

class Candle:
    def __init__(self, ticker, df):
        self.__VALID_COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']
        self.ticker = ticker
        self.data = df[self.__VALID_COLUMNS]

    def __getattr__(self, item):
        if item in self.__VALID_COLUMNS:
            try:
                return self.data[item].to_numpy()
            except:
                return self.data[item]
        elif item == 'index':
            return self.data.index
        else:
            raise IndexError

    def __getitem__(self, item):
        if isinstance(item, slice) or type(item) is int:
            return Candle(self.ticker, self.data.iloc[item, :])

    def __str__(self):
        return f'{self.ticker}-Candle\n'+str(self.data)

    def __len__(self):
        return len(self.data)

    def ma(self, window):
        ma = self.data['Close'].rolling(window=window).mean()
        ma_return = ma.to_list()
        return ma_return

    def ema(self, window):
        list_close = self.data['Close'].to_list()
        ema_0 = list_close[0]
        ema_return = [ema_0]
        for i in range(1, len(list_close)):
            ema_return.append(list_close[i] * (2 / (1 + window)) + (ema_return[i - 1] * (1 - 2 / (1 + window))))
        return ema_return

    def __get_rsi(self, series):
        AU = series.loc[lambda x: x >= 0].sum()
        AD = -series.loc[lambda x: x < 0].sum()
        RS = AU / AD
        return RS / (1 + RS)

    def rsi(self, window):
        rsi_ori = self.data['Close']
        rsi_sub = rsi_ori.shift(periods=1, fill_value=0) - rsi_ori
        rsi = rsi_sub.rolling(window=window).apply(self.__get_rsi)
        rsi_return = rsi.to_list()
        return rsi_return

    def __get_sto_FK(self, series):
        Fast_K = (series.iloc[-1] - series.min()) / (series.max() - series.min()) * 100
        return Fast_K

    def __get_sto_FD_SK(self, series, m):
        Fast_D_Slow_K = series.rolling(window=m).mean()
        return Fast_D_Slow_K

    def __get_sto_SD(self, series, l):
        Slow_D = series.rolling(window=l).mean()
        return Slow_D

    def stch(self, n, m, l):
        fast_K = self.data['Close'].rolling(window=n).apply(self.__get_sto_FK)
        fast_D = self.__get_sto_FD_SK(fast_K, m)
        slow_K = fast_D
        slow_D = self.__get_sto_SD(slow_K, l)

        data_df = pd.concat([fast_K, fast_D, slow_K, slow_D], axis=1)
        data_list = []
        for i in range(4) :
            data_list.append(data_df.iloc[:,i].to_list())
        return data_list

    def __get_ashi(self, ha, df):
        ha_open = (ha[0] + ha[1]) / 2
        ha_close = (np.mean(df))
        ha_high = np.max(ha_open, ha_close, df[2])
        ha_low = np.min(ha_open, ha_close, df[3])

        return [ha_open, ha_close, ha_high, ha_low]

    def ashi(self):
        df = self.data[['Open', 'Close', 'High', 'Low']].to_list()
        ha = [df[0]]
        for i in range(1, len(df)):
            ha.append(self.___get_ashi(ha[i - 1], df[i]))

        return ha


class Mysql:
    def __init__(self, host, user, password, db):
        #데이터베이스에 접속
        self.__host = host
        self.__user = user
        self.__password = password
        self._db = db

    def _connectDB(self):
        self._conn = pymysql.connect(host=self.__host,
                                     user=self.__user,
                                     password=self.__password,
                                     db=self._db,
                                     charset='utf8')

    def _disconnectDB(self):
        self._conn.commit()
        self._conn.close()

    def excute(self):
        self._connectDB()
        out = self._method()
        self._disconnectDB()
        return out

    def _method(self):
        raise NotImplementedError
