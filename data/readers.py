import os
from binance.client import Client
from datetime import datetime
from data.core import Candle, Mysql
import pandas as pd


class BinanceReader:
    def __init__(self, symbol, interval, start, end):  # Client 설정에 필요한 변수들
        self.api_key = os.getenv('Binance_API_KEY')
        self.secret_key = os.getenv('Binance_SECRET_KEY')
        self.client = Client(self.api_key, self.secret_key)
        self.symbol = symbol
        self.interval = interval
        self.start = start
        self.end = end

    def read(self):
        day = self.client.get_historical_klines(symbol=self.symbol, interval=self.interval
        , start_str=int(datetime.strptime(self.start, '%Y-%m-%d %H:%M:%S').timestamp() * 1000)
        , end_str=int(datetime.strptime(self.end, '%Y-%m-%d %H:%M:%S').timestamp()) * 1000)

        columns_df = ['Open time', 'open', 'high', 'low', 'close', 'volume', 'close time', 'Quote', 'N of trades',
                      'Taker buy 1', 'Taker buy 2', 'Ignore']

        df_data = pd.DataFrame(day, columns=columns_df, index=pd.to_datetime([a[0] for a in day], unit='ms'), dtype=float)

        return Candle(self.symbol, df_data)


class SQLReader(Mysql):
    def __init__(self, host, user, password, db):
        super().__init__(host, user, password, db)
        self.ticker = None
        self.interval = None
        self.startDatetime = None
        self.endDatetime = None

    def setTable(self, ticker, interval):
        self.ticker = ticker
        self.interval = interval

    def setDate(self, start=None, end=None):
        if not isinstance(start, datetime) and start is not None:
            try:
                self.startDatetime = datetime.strptime(start, '%Y-%m-%d %H:%M:%S')  # 예시 형식에 맞게 수정
            except ValueError:
                raise ValueError(
                    "Invalid date format. Please provide a valid datetime.datetime object or a string in the format 'YYYY-MM-DD HH:MM:SS'.")
        else:
            self.startDatetime = start
        if not isinstance(end, datetime) and end is not None:
            try:
                self.endDatetime = datetime.strptime(end, '%Y-%m-%d %H:%M:%S')  # 예시 형식에 맞게 수정
            except ValueError:
                raise ValueError(
                    "Invalid date format. Please provide a valid datetime.datetime object or a string in the format 'YYYY-MM-DD HH:MM:SS'.")
        else:
            self.endDatetime = end

    def _method(self):
        if self.startDatetime is None and self.endDatetime is None:
            raise ValueError("One of the Dates must have a value.")
        with self._conn.cursor() as curs:
            if self.startDatetime is not None and self.endDatetime is not None:
                query = f"SELECT * FROM {self.ticker}_{self.interval} WHERE date >= '{self.startDatetime}' AND date <= '{self.endDatetime}'"
            elif self.startDatetime is not None:
                query = f"SELECT * FROM {self.ticker}_{self.interval} WHERE date >= '{self.startDatetime}'"
            else:
                query = f"SELECT * FROM {self.ticker}_{self.interval} WHERE date <= '{self.endDatetime}'"
            curs.execute(query)
            result = curs.fetchall()
        df = pd.DataFrame(result, columns=['index', 'open', 'high', 'low', 'close', 'volume'])
        df.index = df['index']
        df = df.drop(columns=['index'])

        return Candle(self.ticker, df)

    def read(self):
        return self.excute()

