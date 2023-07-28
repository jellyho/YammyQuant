from data.readers import BinanceReader
from envrionment.envs import SimpleBacktestingEnvironment
from trade.agents import MACrossAgent
from trade.core import Trader
import matplotlib.pyplot as plt

reader = BinanceReader('BTCUSDT', '1d', '2022-02-17 00:00:00', '2022-08-17 00:00:00')
env = SimpleBacktestingEnvironment(reader=reader)
env.observeRange = 25
agent = MACrossAgent(5, 20)

trader = Trader(env, agent)
trader.trade()
print(trader.history)

candle = reader.read()
plt.plot(candle.index, candle.ma(5))
plt.plot(candle.index, candle.ma(20))
plt.show()


