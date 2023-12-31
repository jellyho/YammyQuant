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
