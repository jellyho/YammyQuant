import os, time
from binance.client import Client
import pandas as pd
from datetime import datetime
from data.core import Candle


class BinanceReader:
    def __init__(self):  # Client 설정에 필요한 변수들
        self.api_key = os.getenv('Binance_API_KEY')
        self.secret_key = os.getenv('Binance_SECRET_KEY')
        self.client = Client(self.api_key, self.secret_key)

    def read(self, symbol, interval, start, end):
        day = self.client.get_historical_klines(symbol=symbol, interval=interval
        , start_str=int(datetime.strptime(start, '%Y-%m-%d %H:%M:%S').timestamp()*1000)
        , end_str=int(datetime.strptime(end, '%Y-%m-%d %H:%M:%S').timestamp())*1000)

        columns_df = ['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Close time', 'Quote', 'N of trades',
                      'Taker buy 1', 'Taker buy 2', 'Ignore']

        df_data = pd.DataFrame(day, columns=columns_df, index=pd.to_datetime([a[0] for a in day], unit='ms'), dtype=float) # index=pd.DatetimeIndex([a[0] for a in day]))

        return Candle(df_data)
