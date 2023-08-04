# YammyQuant Docs

# 0. Installation

## 1. python depedencies

```python
pip install numpy pandas matplotlib pymysql pyqt5 finta mplfinance python-binance
```

나중에 requirements.txt로 바꾸자

## 2. PATH settings

binance api key 설정하는 법 추가해야함. (python os 모듈 사용해서 간단하게 추가하는것도 만들면 좋을 듯)

# 1. data Module

## 1. data.updaters.SQLUpdater (SQL db 구축하기)

 백테스팅과 알고리즘 개발을 위해서는 먼저 DB에 거래 데이터를 저장해 놓아야 한다. YammyQuant에서는 개인 mysql 서버에 거래 데이터 db를 구축할 수 있도록 해준다.

```python
### example_sqlUpdate.py

from data.updaters import SQLUpdater

updater = SQLUpdater(host='*', user='*', password='*', db='binance')
updater.setTable('ETHUSDT', ['1w', '1d', '6h', '1h', '15m', '5m', '1m'])
updater.update()
```

1. db 이름을 binance로 지정하므로써 binance API를 사용해서 데이터를 불러온다. (다른 거래소 API도 추후 지원하도록 코드 짜야할듯)
2. .setTable(’BTCUSDT’, [’1w’, ‘1d’, …])를 통해서 updater에게 어떤 ticker의 각 interval에 대해서 업데이트 할지 알려준다.
3. .update()를 통해 update 실행

```python
2023-07-29 06:20:04.683781::binance-ETHUSDT-1w last update=>1970-01-02 10:17:36.
2023-07-29 06:20:04.683926::binance-ETHUSDT-1w downloading...
2023-07-29 06:20:04.799147::binance-ETHUSDT-1w download complete.
2023-07-29 06:20:04.808637::binance-ETHUSDT-1w updating(311/311)...
2023-07-29 06:20:04.845477::binance-ETHUSDT-1w update complete.
2023-07-29 06:20:04.958874::binance-ETHUSDT-1d last update=>1970-01-02 10:17:36.
2023-07-29 06:20:04.958983::binance-ETHUSDT-1d downloading...
2023-07-29 06:20:05.244100::binance-ETHUSDT-1d download complete.
2023-07-29 06:20:05.254626::binance-ETHUSDT-1d updating(2173/2173)...
2023-07-29 06:20:05.519638::binance-ETHUSDT-1d update complete.
2023-07-29 06:20:05.658238::binance-ETHUSDT-6h last update=>1970-01-02 10:17:36.
2023-07-29 06:20:05.658358::binance-ETHUSDT-6h downloading...
2023-07-29 06:20:08.642423::binance-ETHUSDT-6h download complete.
2023-07-29 06:20:08.650292::binance-ETHUSDT-6h updating(8684/8684)...
2023-07-29 06:20:09.826637::binance-ETHUSDT-6h update complete.
2023-07-29 06:20:09.961169::binance-ETHUSDT-1h last update=>1970-01-02 10:17:36.
2023-07-29 06:20:09.961291::binance-ETHUSDT-1h downloading...
2023-07-29 06:20:32.987504::binance-ETHUSDT-1h download complete.
2023-07-29 06:20:32.997861::binance-ETHUSDT-1h updating(10000/52003)...
2023-07-29 06:20:34.163404::binance-ETHUSDT-1h updating(20000/52003)...
2023-07-29 06:20:35.432261::binance-ETHUSDT-1h updating(30000/52003)...
2023-07-29 06:20:36.252786::binance-ETHUSDT-1h updating(40000/52003)...
2023-07-29 06:20:37.109443::binance-ETHUSDT-1h updating(50000/52003)...
2023-07-29 06:20:37.906069::binance-ETHUSDT-1h updating(52003/52003)...
2023-07-29 06:20:38.070265::binance-ETHUSDT-1h update complete.
2023-07-29 06:20:38.256104::binance-ETHUSDT-15m last update=>1970-01-02 10:17:36.
2023-07-29 06:20:38.256299::binance-ETHUSDT-15m downloading...
```

이런 식으로 업데이트가 진행 된다. (맨 처음 업데이트시 오래걸릴 수 있음)

앞으로 다른 거래소의 db를 업데이트 하는 경우에 대한 코드도 추가하면 좋을 듯 하다.

## 2. data.readers.SQLReader (SQL 읽기)

```python
### example_sqlRead.py

from data.readers import SQLReader

reader = SQLReader(host='*', user='*', password='*', db='binance')
print(reader.getInfo())

reader.setTable('BTCUSDT', '1d')
reader.setDate('2022-02-17 00:00:00', '2022-08-17 00:00:00')

candle = reader.read()
print(candle)
```

sqlUpdater로 구축된 데이터를 다시 불러오는 모듈이다.

1. reader를 생성한다. db이름에 유의. binance데이터를 불러오기 위해서는 ‘binance’라고 입력해야한다.
2. .getInfo()를 통해서 현재 db에 저장된 코인이름(ticker)와 ticker 별 interval을 dictionary 형태로 반환한다. 어떤 코인을 불러올 수 있는지 확인하기 위해 사용
3. .setTable을 통해 불러올 코인이름(ticker)와 간격(interval)을 지정해 준다.
4. .setDate를 통해 불러올 데이터의 시작 시간과 끝 시간을 넣어준다. str와 datetime.datetime 객체로 넣어줄 수 있으며, str 형식으로 넣을 경우 `'%Y-%m-%d %H:%M:%S'` 형태로 넣어주어야 한다.
시작 시간이 None이고 끝 시간을 넣어주는 경우 db의 첫 데이터부터 끝 시간까지 불러오며, 끝 시간이 None이고 시작 시간을 넣어주는 경우 시작 시간부터 db의 마지막 데이터까지 불러온다. 두개 모두 None일 경우 ValueError.
5. .read()를 통해 데이터를 불러온다. 반환 타입은 data.core.Candle 이다.

```python
{'BTCUSDT': ['15m', '1d', '1h', '1m', '1w', '5m', '6h'], 'ETHUSDT': ['15m', '1d', '1h', '1m', '1w', '5m', '6h'], 'XRPUSDT': ['15m', '1d', '1h', '1m', '1w', '5m', '6h']}
BTCUSDT-Candle
               open     high      low    close    volume
index                                                   
2022-02-17  43873.6  44164.7  40073.2  40515.7   47246.0
2022-02-18  40515.7  40959.9  39450.0  39974.4   43845.9
2022-02-19  39974.4  40444.3  39639.0  40079.2   18042.1
2022-02-20  40079.2  40125.4  38000.0  38386.9   33439.3
2022-02-21  38386.9  39494.4  36800.0  37008.2   62347.7
...             ...      ...      ...      ...       ...
2022-08-13  24401.7  24888.0  24291.2  24441.4  152852.0
2022-08-14  24443.1  25047.6  24144.0  24305.2  151206.0
2022-08-15  24305.2  25211.3  23773.2  24094.8  242540.0
2022-08-16  24093.0  24247.5  23671.2  23854.7  179325.0
2022-08-17  23856.2  24446.7  23180.4  23342.7  210669.0

[182 rows x 5 columns]
```

실행결과.

## 3. data.readers.BinanceReader

sql에서 읽는 것이 아니라 Binance API를 이용해서 읽을 수 있도록 만든 reader이다. binance api 보다 편하게 사용할 수 있도록, 그리고 반환 객체가 data.core.Candle 객체가 되도록 하는것이 목표.
 

```python
from data.readers import BinanceReader

reader = BinanceReader()
reader.setTicker('BTCUSDT')
reader.setInterval('1d')
reader.setDate('2022-02-17 00:00:00', '2022-08-17 00:00:00')
candle = reader.read()
```
setDate를 안해줄 경우 그냥 제일 최근 값 가져오도록 했다.

## 4. data.core.Candle

거래 시계열 데이터를 쉽게 다룰 수 있게 하기 위해서 만든 클래스. 기본적으로 pandas.Dataframe의 wrapper겪이다.

```python
from data.core import Candle

candle = Candle('BTCUSDT', df)
```

이런식으로 이름과 데이터프레임을 넣어서 생성한다. 데이터프레임에는 기본적으로 `['open', 'high', 'low', 'close', 'volume']` column이 존재해야하며 그 외의 column은 있어도 삭제된다.

candle.data로 데이터프레임에 직접 접근 가능

```python
candle.open
candle.high
candle.low
candle.close
candle.volume
candle.index
```

각 column과 index 접근 가능 (slice indexing도 마찬가지로 가능하다)

candle 클래스에 finta의 TA들 wrapper를 구현해 놓았다.

[https://github.com/peerchemist/finta](https://github.com/peerchemist/finta)

github를 참고하여 다양한 TA를 사용할 수 있다. github에서는 TA.SMA(ohlc, 42)로 사용했다면 대신에 candle.SMA(42)와 같이 사용할 수 있다.

아래 예시 참고

```python
###example_candle_indicators.py
import matplotlib.pyplot as plt
from data.readers import BinanceReader

reader = BinanceReader()
reader.setTicker('BTCUSDT')
reader.setInterval('1d')
reader.setDate('2022-02-17 00:00:00', '2022-08-17 00:00:00')
candle = reader.read()

plt.plot(candle.index, candle.SMA(5))
plt.plot(candle.index, candle.SMA(20))
plt.show()
```
