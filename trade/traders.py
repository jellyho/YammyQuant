from trade.core import Trader
from trade.utils import Action as a
import os
from binance.client import Client


class BinanceMarketTrader(Trader):
    def __init__(self):
        super().__init__()
        api_key = os.getenv('Binance_API_KEY')
        secret_key = os.getenv('Binance_SECRET_KEY')
        self.client = Client(api_key, secret_key)

    def _trade_method(self, order):
        try:
            if order['action'] != a.HOLD:
                result = self.client.create_order(
                    symbol=order['ticker'],
                    side=order['action'],
                    type='MARKET',
                    quantity=order['quantity'])
                if result['status'] == 'FILLED':
                    order.fill(fill=result['executedQty'], fee=result['commision'], ID=order['orderId'])
                else:
                    pass
            else: # Hold...
                order.fill()
            return order
        except:
            return False


class BackTestingTrader(Trader):
    # BackTestingTrader : Simply fills the order no matter what order received.
    def __init__(self):
        super().__init__()

    def _trade_method(self, order):
        try:
            order.fill()
            return order
        except:
            return False