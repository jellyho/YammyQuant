from data.readers import SQLReader
from envrionment.envs import SimpleBacktestingEnvironment
from trade.agents import VotalityBreakoutAgent
from trade.traders import BackTestingTrader
from trade.utils import Portfolio
import matplotlib.pyplot as plt

reader = SQLReader(json_dir='sql.json')
reader.setTicker('BTCUSDT')
reader.setInterval('1h')
reader.setDate('2023-01-01 00:00:00', '2023-06-30 00:00:00')

env = SimpleBacktestingEnvironment(reader=reader)
env.observeRange = 25
agent = VotalityBreakoutAgent(0.6)

trader = BackTestingTrader()
port = Portfolio(100000, env.tradeFee)
trader.setEnv(env)
trader.setAgent(agent)
trader.setPortfolio(port)

trader.trade()

print(trader.portfolio.history)

trader.portfolio.history.to_csv('result.csv')
candle = reader.read()
plt.plot(candle.index, candle.close)
plt.show()