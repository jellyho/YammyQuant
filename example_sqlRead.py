from data.readers import SQLReader

reader = SQLReader(host='jellyho.iptime.org', user='yammyquant', password='dialfl752', db='binance')
reader.setTable('BTC', '1_DAY')
reader.setDate('2022-02-17 00:00:00', '2022-08-17 00:00:00')

candle = reader.read()
print(candle)
