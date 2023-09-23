from data.readers import BinanceReader
from envrionment.envs import SimpleBacktestingEnvironment
from trade.agents import MACrossAgent
from trade.core import Trader
import matplotlib.pyplot as plt

reader = BinanceReader()
reader.setTicker('BTCUSDT')
reader.setInterval('15m')
reader.setDate('2023-02-17 00:00:00', '2023-03-17 00:00:00')

env = SimpleBacktestingEnvironment(reader=reader)
env.observeRange = 25
agent = MACrossAgent(5, 20)

trader = Trader(env, agent)
trader.trade()
trader.history.show()

candle = reader.read()
plt.plot(candle.index, candle.SMA(5))
plt.plot(candle.index, candle.SMA(20))
plt.show()


