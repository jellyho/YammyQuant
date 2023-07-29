import pymysql
from finta import TA

intervalList = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '1w', '1M']

class Candle:
    def __init__(self, ticker, df):
        self.__VALID_COLUMNS = ['open', 'high', 'low', 'close', 'volume']
        self.ticker = ticker
        self.data = df[self.__VALID_COLUMNS]
        self.TAs = [func for func in dir(TA) if callable(getattr(TA, func))]

    def __getattr__(self, item):
        if item in self.__VALID_COLUMNS:
            try:
                return self.data[item].to_numpy()
            except:
                return self.data[item]
        elif item == 'index':
            return self.data.index
        elif item in self.TAs:
            method = getattr(TA, item)

            def ta_method(*args):
                return method(self.data, *args)

            return ta_method
        else:
            raise IndexError

    def __getitem__(self, item):
        if isinstance(item, slice) or type(item) is int:
            return Candle(self.ticker, self.data.iloc[item, :])

    def __str__(self):
        return f'{self.ticker}-Candle\n'+str(self.data)

    def __len__(self):
        return len(self.data)


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
                                     charset='utf8', connect_timeout=36000)

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
