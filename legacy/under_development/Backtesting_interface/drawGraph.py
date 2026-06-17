import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
from useClass import Indicator

#from SQL에서 소환하는 파일 import 불러오는거 <- 이거 아직 잘 확인안해서 추후에 넣으면될듯


class Draw :
    def __init__(self,data,earn) :
        self.data = data
        self.earn = earn
        self.start = 100
    
    def get_indicator(self) :
        self.Indi = Indicator(self.data)
        self.ma_5 = self.Indi.ma(5)
        self.ma_20 = self.Indi.ma(20)
        self.ma_60 = self.Indi.ma(60)
        self.vol = self.data['Volume']
    
    def get_earn(self) :
        self.accum, self.sho = self.Indi.cal_earn(self.earn,self.start)
        self.index = []
        for _ in range(self.earn) :
            if abs(self.earn[_]) == 1 :
                self.index.append(_)
        if len(self.index) % 2 == 1 :
            self.index.append(len(self.earn)-1)
        

    def draw(self) :
        fig = make_subplots(rows=4,cols=1,row_heights=[0.5,0.1,0.2,0.2])
        fig.update_layout(width=720,height=720)
        fig.add_trace(go.Candlestick(x=self.data.index,open=self.data['Open'],high=self.data['High'],low=self.data['Low'],close=self.data['Close']
                                     ,increasing_fillcolor='green'
                                     ,increasing_linecolor='green'
                                     ,decreasing_fillcolor='red'
                                     ,decreasing_linecolor='red')
                                     ,row=1,col=1)
        fig.add_trace(go.Line(self.ma_5,color='yellow'),row=1,col=1)
        fig.add_trace(go.Line(self.ma_20,color='blue'),row=1,col=1)
        fig.add_trace(go.Line(self.ma_60,color='purple'),row=1,col=1)
        fig.add_trace(go.Bar(self.vol),row=2,col=1)
        fig.add_trace(go.Line(self.accum),row=3,col=1)
        fig.add_trace(go.Line(self.sho),row=4,col=1)

        for _ in range(len(self.index)/2) :
            fig.add_vrect(x0=self.data.index[self.index[2*_]],x1=self.data.index[self.index[2*_+1]],
                          fillcolor = 'green' if self.data['Close'][self.index[2*_]-1] >= self.data['Close'][self.index[2*_+1]-1] else 'red',
                          opcaity = 0.1,row=3,col=1)
            fig.add_vrect(x0=self.data.index[self.index[2*_]],x1=self.data.index[self.index[2*_+1]],
                          fillcolor = 'green' if self.data['Close'][self.index[2*_]-1] <= self.data['Close'][self.index[2*_+1]-1] else 'red',
                          opcaity = 0.1,row=4,col=1)
            fig.add_shape(type="rect",
                          x0=self.data.index[self.index[2*_]],x1=self.data.index[self.index[2*_+1]],
                          y0=self.data['close'][self.index[2*_]-1], y1=self.data['Close'][self.index[2*_+1]-1],
                          fillcolor = 'green' if self.data['Close'][self.index[2*_]-1] <= self.data['Close'][self.index[2*_+1]-1] else 'red',
                          opacity=0.1,row=1,col=1)
            




