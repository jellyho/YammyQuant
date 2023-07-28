import matplotlib.pyplot as plt
from data.readers import BinanceReader

reader = BinanceReader('BTCUSDT', '1d', '2022-02-17 00:00:00', '2022-08-17 00:00:00')
candle = reader.read()
plt.plot(candle.index, candle.ma(5))
plt.plot(candle.index, candle.ma(20))
plt.show()
