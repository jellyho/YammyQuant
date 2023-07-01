import os
from binance.client import Client
import pandas as pd
import time
from datetime import datetime


class getDATA:

    def __init__(self, symbol, interval, start_str, limit):  # Client 설정에 필요한 변수들
        self.symbol = symbol
        self.interval = interval
        self.start_str = start_str
        self.limit = limit
        self.api_key = os.getenv('Binance_API_KEY')
        self.secret_key = os.getenv('Binance_SECRET_KEY')

    def get_candle_dataframe(self, num):

        client = Client(self.api_key, self.secret_key)

        interval_timestamp = {'1m': 60000, '5m': 300000, '15m': 900000, '1h': 3600000, '4h': 14400000, '1d': 86400000,
                              '1w': 604800000}

        now_timestamp = int(time.mktime(datetime.now())) * 1000
        need_timestamp = int(
            now_timestamp - now_timestamp % interval_timestamp[self.interval] - interval_timestamp[self.interval] * (
                        num - 1))

        day = client.get_historical_klines(
            symbol=self.symbol,
            interval=self.interval,
            start_str=need_timestamp,
            limit=self.limit
        )

        columns_df = ['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote', 'N of trades',
                      'Taker buy 1', 'Taker buy 2', 'Ignore']
        index_df = []

        for a in day:
            index_df.append(a[0])

        df_data = pd.DataFrame(day, columns=columns_df, index=index_df)

        return df_data

    def update_candle_csv(self, filename_pass):

        interval_timestamp = {'1m': 60000, '5m': 300000, '15m': 900000, '1h': 3600000, '4h': 14400000, '1d': 86400000,
                              '1w': 604800000}

        data_origin = pd.read_csv(filename_pass)
        remove_column = data_origin.columns.to_list
        last_timestamp = data_origin.index.to_list[-1]

        new_start = last_timestamp + interval_timestamp[self.interval]

        api_key = os.getenv('Binance_API_KEY')
        secret_key = os.getenv('Binance_SECRET_KEY')

        client = Client(api_key, secret_key)

        day = client.get_historical_klines(
            symbol=self.symbol,
            interval=self.interval,
            start_str=new_start,
            limit=self.limit
        )

        columns_df = ['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote', 'N of trades',
                      'Taker buy 1', 'Taker buy 2', 'Ignore']
        index_df = []

        for a in day:
            index_df.append(a[0])

        data_get = pd.DataFrame(day, columns=columns_df, index=index_df)

        data_plus = data_get.drop(remove_column, axis='columns')

        data_new = pd.concat([data_origin, data_plus], axis=0, ignore_index=False)

        data_new.to_csv(filename_pass)