from data.updaters import SQLUpdater
import time


updater = SQLUpdater(host='jellyho.iptime.org', user='yammyquant', password='dialfl752', db='binance')
updater.setTable('BTCUSDT', ['1w', '1d', '6h', '1h', '15m', '5m', '1m'])

while True:
    try:
        updater.update()
    except:
        print('error occurred')
    time.sleep(3600 * 6)
