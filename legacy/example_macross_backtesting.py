from data.readers import SQLReader
from envrionment.envs import SimpleBacktestingEnvironment
from trade.agents import MACrossAgent
from trade.traders import BackTestingTrader
from trade.utils import Portfolio
from filtering_data import drawGraph
import matplotlib.pyplot as plt


reader = SQLReader(json_dir='sql.json')
reader.setTicker('XRPUSDT')
reader.setInterval('5m')
reader.setDate('2023-05-01 00:00:00', '2023-05-03 00:00:00')

env = SimpleBacktestingEnvironment(reader=reader)
env.observeRange = 25
agent = MACrossAgent(5, 20)

trader = BackTestingTrader()
port = Portfolio(80, env.tradeFee)
trader.setEnv(env)
trader.setAgent(agent)
trader.setPortfolio(port)

trader.trade()

print(trader.portfolio.history)

trader.portfolio.history.to_csv('result.csv')
candle = reader.read()
datasave = drawGraph(trader.portfolio.history, candle.data, {'ma5' : candle.SMA(5), 'ma20' : candle.SMA(20), 'rsi10' : candle.RSI(10)})
datasave.filtering()