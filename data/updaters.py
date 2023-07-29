import os
from datetime import datetime
from data.core import Candle, Mysql
import pandas as pd


class SQLUpdater(Mysql):
    def setTable(self, ticker, intervals):
        self.ticker = ticker
        self.intervals = intervals
        self.__maxRows = 10000

    def _method(self):
        if self._db == 'binance':
            from binance.client import Client
            self.api_key = os.getenv('Binance_API_KEY')
            self.secret_key = os.getenv('Binance_SECRET_KEY')
            self.client = Client(self.api_key, self.secret_key)

            for interval in self.intervals:
                # table이 없다면 생성하고 가장 마지막 저장된 데이터 이후 부터 업데이트
                with self._conn.cursor() as curs:
                    sql = f"""
                    create table if not exists {self.ticker}_{interval} (
                    date TIMESTAMP,
                    open FLOAT,
                    high FLOAT,
                    low FLOAT,
                    close FLOAT,
                    volume FLOAT,
                    PRIMARY KEY (date)
                    )
                    """
                    curs.execute(sql)
                    self._conn.commit()
                    query = f'SELECT MAX(date) FROM {self.ticker}_{interval}'
                    curs.execute(query)
                    result = curs.fetchall()[0][0]
                self._disconnectDB()
                if result is None:
                    result = datetime.fromtimestamp(123456.0)
                print(f'{datetime.now()}::{self._db}-{self.ticker}-{interval} last update=>{result}.')
                print(f'{datetime.now()}::{self._db}-{self.ticker}-{interval} downloading...')
                data = self.client.get_historical_klines(symbol=self.ticker, interval=interval, start_str=int(result.timestamp() * 1000))
                columns_df = ['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote', 'N of trades', 'Taker buy 1', 'Taker buy 2', 'Ignore']
                df = pd.DataFrame(data, columns=columns_df, index=pd.to_datetime([a[0] for a in data], unit='ms'), dtype=float)
                print(f'{datetime.now()}::{self._db}-{self.ticker}-{interval} download complete.')

                idx_start = 0
                idx_end = 0
                self._connectDB()
                while idx_end < len(df):
                    if idx_start + self.__maxRows > len(df):
                        idx_end = len(df)
                    else:
                        idx_end = idx_start + self.__maxRows
                    print(f'{datetime.now()}::{self._db}-{self.ticker}-{interval} updating({idx_end}/{len(df)})...')
                    with self._conn.cursor() as curs:
                        sql = f"REPLACE INTO {self.ticker}_{interval} (date, open, high, low, close, volume) VALUES "
                        for r in df[idx_start:idx_end].itertuples():
                            sql += f"('{r.Index}', {r.Open}, {r.High}, {r.Low}, {r.Close}, {r.Volume}), "
                        sql = sql[:-2]
                        curs.execute(sql)
                    idx_start = idx_start + self.__maxRows
                print(f'{datetime.now()}::{self._db}-{self.ticker}-{interval} update complete.')

    def update(self):
        self.excute()
