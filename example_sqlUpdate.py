from data.updaters import SQLUpdater

updater = SQLUpdater(host='jellyho.iptime.org', user='yammyquant', password='dialfl752', db='binance')
updater.setTable('BTCUSDT', ['1w', '1d', '6h', '1h', '15m', '5m', '1m'])
updater.update()
