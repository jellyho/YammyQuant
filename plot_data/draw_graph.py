from plotly.subplots import make_subplots
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

def make_str(x):
    if x>0:
        sign = 'buy'
    else:
        sign = 'sell'
    return sign

sub_indi = pd.read_csv('plot_data/sub_indi.csv',index_col=0)
main_indi = pd.read_csv('plot_data/main_indi.csv',index_col=0)
main_indi['vSign'] = main_indi['vSign'].apply(make_str)
cash = pd.read_csv('plot_data/cash.csv',index_col='time')
trade = pd.read_csv('plot_data/trade.csv',index_col='time')

fig = make_subplots(rows=3, cols=1, row_heights=[0.9,0.05,0.05], column_widths=[1], subplot_titles=("Main","Sub","Seed"), shared_xaxes=True, specs=[[{'secondary_y':True}],[{'secondary_y':False
}],[{'secondary_y':False}]])
buy = main_indi.query('vSign=="buy"')
sell = main_indi.query('vSign=="sell"')
fig.add_trace(go.Bar(x=buy.index, y=buy['volume'],marker={'color':'green'}))
fig.add_trace(go.Bar(x=sell.index, y=sell['volume'],marker={'color':'crimson'}))
fig.add_trace(go.Scatter(x=main_indi.index, y=main_indi['open'], mode='lines', name='openPrice'), row=1, col=1, secondary_y=True)
fig.add_trace(go.Scatter(x=cash.index, y=cash['ticker_meanPrice'],name='meanPrice',line_shape='hv', mode='lines'), row=1, col=1, secondary_y=True)
fig.update_yaxes(range=[0,50000],secondary_y=False)

if len(main_indi.columns)>6:
    for _ in range(5,len(main_indi.columns)-1):
        fig.add_trace(go.Scatter(x=main_indi.index, y=main_indi.iloc[:,_],mode='lines',name=main_indi.columns[_], line=dict(width=1)),row=1,col=1,secondary_y=True)

fig.show()
  