from data.readers import SQLReader
from envrionment.envs import SimpleBacktestingEnvironment
from trade.agents import MACrossAgent
from trade.traders import BackTestingTrader
from trade.utils import Portfolio
import matplotlib.pyplot as plt

reader = SQLReader(json_dir='sql.json')
reader.setTicker('XRPUSDT')
reader.setInterval('5m')
reader.setDate('2023-05-01 00:00:00', '2023-05-03 00:00:00')

env = SimpleBacktestingEnvironment(reader=reader)
env.observeRange = 25
agent = MACrossAgent(5, 20)

trader = BackTestingTrader()
port = Portfolio(100000, env.tradeFee)
trader.setEnv(env)
trader.setAgent(agent)
trader.setPortfolio(port)

trader.trade()

print(trader.portfolio.history)

trader.portfolio.history.to_csv('result.csv')
candle = reader.read()
plt.plot(candle.index, candle.SMA(5))
plt.plot(candle.index, candle.SMA(20))
plt.show()