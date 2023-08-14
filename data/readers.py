import os
from binance.client import Client
from datetime import datetime
from data.core import Candle, Mysql
import pandas as pd


class BinanceReader:
    def __init__(self):  # Client 설정에 필요한 변수들
        api_key = os.getenv('Binance_API_KEY')
        secret_key = os.getenv('Binance_SECRET_KEY')
        self.client = Client(self.api_key, self.secret_key)
        self.ticker = None
        self.interval = None
        self.start = None
        self.end = None

    def setTicker(self, ticker):
        ticker_list = self.client.get_all_tickers()
        ticker_list = [t['symbol'] for t in ticker_list]
        if ticker in ticker_list:
            self.ticker = ticker
        else:
            raise ValueError("Invalid Ticker")

    def setInterval(self, interval):
        self.interval = interval

    def setDate(self, start=None, end=None):
        if not isinstance(start, datetime) and start is not None:
            try:
                self.start = datetime.strptime(start, '%Y-%m-%d %H:%M:%S').timestamp() * 1000  # 예시 형식에 맞게 수정
            except ValueError:
                raise ValueError(
                    "Invalid date format. Please provide a valid datetime.datetime object or a string in the format 'YYYY-MM-DD HH:MM:SS'.")
        else:
            self.start = start.timestamp() * 1000
        if not isinstance(end, datetime) and end is not None:
            try:
                self.end = datetime.strptime(end, '%Y-%m-%d %H:%M:%S').timestamp() * 1000  # 예시 형식에 맞게 수정
            except ValueError:
                raise ValueError(
                    "Invalid date format. Please provide a valid datetime.datetime object or a string in the format 'YYYY-MM-DD HH:MM:SS'.")
        else:
            self.end = end.timestamp() * 1000

    def read(self):
        if self.start is None and self.end is None:
            day = self.client.get_klines(symbol=self.ticker, interval=self.interval)
        else:
            day = self.client.get_historical_klines(symbol=self.ticker, interval=self.interval, start_str=int(self.start), end_str=int(self.end))

        columns_df = ['Open time', 'open', 'high', 'low', 'close', 'volume', 'close time', 'Quote', 'N of trades',
                      'Taker buy 1', 'Taker buy 2', 'Ignore']

        df_data = pd.DataFrame(day, columns=columns_df, index=pd.to_datetime([a[0] for a in day], unit='ms'), dtype=float)

        return Candle(self.ticker, df_data)


class SQLReader(Mysql):
    def __init__(self, host, user, password, db):
        super().__init__(host, user, password, db)
        self.ticker = None
        self.interval = None
        self.startDatetime = None
        self.endDatetime = None

    def getInfo(self):
        self._connectDB()
        with self._conn.cursor() as curs:
            curs.execute('SHOW TABLES')
            result = curs.fetchall()
        self._disconnectDB()
        result = [r[0] for r in list(result)]
        result_dict = {}
        for r in result:
            ticker_interval = r.split('_')
            try:
                result_dict[ticker_interval[0]]
            except:
                result_dict[ticker_interval[0]] = []
            finally:
                result_dict[ticker_interval[0]].append(ticker_interval[1])
        return result_dict

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

