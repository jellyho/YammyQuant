from data.updaters import SQLUpdater
import time

updater1 = SQLUpdater(host='jellyho.iptime.org', user='yammyquant', password='dialfl752', db='binance')
updater1.setTable('BTCUSDT', ['1w', '1d', '6h', '1h', '15m', '5m', '1m'])
updater2 = SQLUpdater(host='jellyho.iptime.org', user='yammyquant', password='dialfl752', db='binance')
updater2.setTable('ETHUSDT', ['1w', '1d', '6h', '1h', '15m', '5m', '1m'])

while True:
    try:
        updater1.update()
        updater2.update()
    except:
        print('error occurred')
    time.sleep(3600 * 6)
