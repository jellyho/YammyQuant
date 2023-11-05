from data.readers import BinanceReader
from envrionment.envs import SimpleBacktestingEnvironment
from trade.agents import MACrossAgent
from trade.traders import BackTestingTrader
from trade.utils import Portfolio
import matplotlib.pyplot as plt
from plot_history import drawGraph

reader = BinanceReader()
reader.setTicker('BTCUSDT')
reader.setInterval('15m')
reader.setDate('2023-02-17 00:00:00', '2023-03-17 00:00:00')

env = SimpleBacktestingEnvironment(reader=reader)
env.observeRange = 25
agent = MACrossAgent(5, 20)

trader = BackTestingTrader()
port = Portfolio(1000000, 0.01)
trader.setEnv(env)
trader.setAgent(agent)
trader.setPortfolio(port)

trader.trade()

print(trader.portfolio.history)

trader.portfolio.history.to_csv('result.csv')
candle = reader.read()

indicator = dict(ma_5 = candle.SMA(5), ma_20 = candle.SMA(20), rsi_5 = candle.RSI(5), rsi_20 = candle.RSI(20))

graph = drawGraph(trader.portfolio.history, candle.data, indicator)
graph.filtering()

