import matplotlib.pyplot as plt
from data.readers import BinanceReader

reader = BinanceReader()
candle = reader.read('BTCUSDT', '1d', '2023-03-17 00:00:00', '2023-05-17 00:00:00')
plt.plot(candle.index, candle.Close)
plt.plot(candle.index, candle.ma(4))
plt.show()
