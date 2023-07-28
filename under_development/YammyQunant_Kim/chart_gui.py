import pymysql
import pandas as pd
import mplfinance as mpf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton, QLineEdit, QTextEdit, QMessageBox, QComboBox
from PyQt5.QtCore import Qt
from datetime import datetime



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # SQLAlchemy 엔진 생성
        pymysql.install_as_MySQLdb()
        daily_engine = create_engine("mysql+mysqldb://yammyquant:dialfl752@jellyho.iptime.org:3306/binance",
                                     encoding='utf-8')

        # 세션 생성
        Session = sessionmaker(bind=daily_engine)
        self.session = Session()

        self.setWindowTitle("BTC Data Viewer")
        self.setGeometry(100, 100, 900, 600)

        # 레이아웃 설정
        layout = QVBoxLayout()
        self.widget = QWidget()
        self.widget.setLayout(layout)
        self.setCentralWidget(self.widget)

        self.instructions_label = QLabel(
            "After값을 조회하고 싶으면 Start Date, Before값을 조회하고 싶으면 End Date에만 값을 입력하세요.")
        layout.addWidget(self.instructions_label)
        

        # 시작 타임스탬프 입력 필드
        self.start_timestamp_label = QLabel("Start Date:")
        layout.addWidget(self.start_timestamp_label)
        self.start_timestamp_edit = QLineEdit()
        layout.addWidget(self.start_timestamp_edit)

        # 끝 타임스탬프 입력 필드
        self.end_timestamp_label = QLabel("End Date:")
        layout.addWidget(self.end_timestamp_label)
        self.end_timestamp_edit = QLineEdit()
        layout.addWidget(self.end_timestamp_edit)

        # 조회 버튼
        self.query_button1 = QPushButton("Between")
        self.query_button1.setToolTip("이 버튼은 입력한 두 시간 사이의 데이터를 불러옵니다.")
        self.query_button1.clicked.connect(self.query_data_between)
        layout.addWidget(self.query_button1)
        self.query_button1.setStyleSheet(
            "QPushButton { background-color: white; color: black; border-radius: 8px; height: 20px;}")

        self.query_button2 = QPushButton("After")
        self.query_button2.setToolTip("이 버튼은 입력한 시간 이후의 데이터를 불러옵니다. Start Date에만 값을 입력해주세요.")
        self.query_button2.clicked.connect(self.query_data_after)
        layout.addWidget(self.query_button2)
        self.query_button2.setStyleSheet(
            "QPushButton { background-color: red; color: white; border-radius: 8px; height: 20px;}")

        self.query_button3 = QPushButton("Before")
        self.query_button3.setToolTip("이 버튼은 입력한 시간 이전의 데이터를 불러옵니다. End Date에만 값을 입력해주세요.")
        self.query_button3.clicked.connect(self.query_data_before)
        layout.addWidget(self.query_button3)
        self.query_button3.setStyleSheet(
            "QPushButton { background-color: blue; color: white; border-radius: 8px; height: 20px;}")
        
        # QComboBox 설정
        self.combo_box = QComboBox()
        self.combo_box.addItems(['BTCUSDT_1m', 'BTCUSDT_5m', 'BTCUSDT_15m', 'BTCUSDT_1h', 'BTCUSDT_6h', 'BTCUSDT_1d', 'BTCUSDT_1w'])  # 필요한 옵션을 추가
        layout.addWidget(self.combo_box)


        # 결과 출력창
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)

        self.msg_box = QMessageBox(self)



##########################################################################################################################################




    # Between 데이터 조회 및 차트 그리기
    def query_data_between(self):
        selected_option = self.combo_box.currentText()  # 선택된 옵션 가져오기

        start_date_input = self.start_timestamp_edit.text().strip()
        end_date_input = self.end_timestamp_edit.text().strip()

        # 값이 비어 있는지 확인
        if not start_date_input:
            self.msg_box.warning(self, "Error", "Start Date를 입력하세요.")
            return
        elif not end_date_input:
            self.msg_box.warning(self, "Error", "End Date를 입력하세요.")
            return

        # 입력된 날짜 문자열을 날짜 형식으로 변환
        try:
            start_date = datetime.strptime(start_date_input, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_input, "%Y-%m-%d").date()
        except ValueError:
            self.msg_box.warning(self, "Error", "올바른 날짜 형식(YYYY-MM-DD)으로 입력하세요.")
            return

        # SQL 쿼리(a <= x <= b) 실행
        query = f"SELECT * FROM {selected_option} WHERE date >= '{start_date}' AND date <= '{end_date}'"
        result = self.session.execute(query)


        row_list = list(result)

        modified_list = []  # row_list는 immutable 객체이므로 데이터를 담을 새로운 list 생성


        for row in row_list:
            timestamp = int(datetime.timestamp(row[0])) # DB table에 date를 timestamp로 변환
            datetime_obj = datetime.fromtimestamp(timestamp)

            # 튜플 언패킹으로 첫 번째 요소를 datetime_obj로 대체(timestamp를 datetime으로 변환한 것 + OHLCV + N_of_trades)
            modified_row = (datetime_obj,) + row[1:]
            modified_list.append(modified_row)
    
        # 결과 출력
        self.result_text.clear()
        self.result_text.append(f"데이터를 조회한 결과 총 {len(modified_list)}개의 데이터가 있습니다.")
        self.result_text.append("")
    
        if len(modified_list) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return
    
        for row in modified_list:
            datetime_str = row[0].strftime("%Y-%m-%d %H:%M:%S")  # 시간 형식 변경
            BTC_data = (datetime_str,) + row[1:]
            self.result_text.append(str(BTC_data))
    
        # DataFrame으로 변환
        df = pd.DataFrame(modified_list, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"])  # 인덱스를 datetime 형식으로 변환
        df.set_index("Date", inplace=True)
    
        if len(df) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return
    
        # 캔들 차트 그리기
        mc = mpf.make_marketcolors(up='r', down='b')  # 가격이 올랐을 때는 빨강, 내렸을 때는 파랑으로 설정
        s = mpf.make_mpf_style(marketcolors=mc)
        mpf.plot(df, type='candle', title=f'{selected_option} Chart', ylabel='Price', volume=True, style=s, datetime_format='%Y-%m-%d %H:%M:%S')







##########################################################################################################################################




    # After 데이터 조회 및 차트 그리기
    def query_data_after(self):
        selected_option = self.combo_box.currentText()  # 선택된 옵션 가져오기

        start_date_input = self.start_timestamp_edit.text().strip()


        # 값이 비어 있는지 확인
        if not start_date_input:
            self.msg_box.warning(self, "Error", "Start Date를 입력하세요.")
            return
        

        # 입력된 날짜 문자열을 날짜 형식으로 변환
        try:
            start_date = datetime.strptime(start_date_input, "%Y-%m-%d").date()
        except ValueError:
            self.msg_box.warning(self, "Error", "올바른 날짜 형식(YYYY-MM-DD)으로 입력하세요.")
            return

        # SQL 쿼리(a <= x <= b) 실행
        query_after = f"SELECT * FROM {selected_option} WHERE date >= '{start_date}'"
        result = self.session.execute(query_after)


        row_list = list(result)

        modified_list = []  # row_list는 immutable 객체이므로 데이터를 담을 새로운 list 생성


        for row in row_list:
            timestamp = int(datetime.timestamp(row[0])) # DB table에 date를 timestamp로 변환
            datetime_obj = datetime.fromtimestamp(timestamp)

            # 튜플 언패킹으로 첫 번째 요소를 datetime_obj로 대체(timestamp를 datetime으로 변환한 것 + OHLCV + N_of_trades)
            modified_row = (datetime_obj,) + row[1:]
            modified_list.append(modified_row)
    
        # 결과 출력
        self.result_text.clear()
        self.result_text.append(f"데이터를 조회한 결과 총 {len(modified_list)}개의 데이터가 있습니다.")
        self.result_text.append("")
    
        if len(modified_list) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return
    
        for row in modified_list:
            datetime_str = row[0].strftime("%Y-%m-%d %H:%M:%S")  # 시간 형식 변경
            BTC_data = (datetime_str,) + row[1:]
            self.result_text.append(str(BTC_data))
    
        # DataFrame으로 변환
        df = pd.DataFrame(modified_list, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"])  # 인덱스를 datetime 형식으로 변환
        df.set_index("Date", inplace=True)
    
        if len(df) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return
    
        # 캔들 차트 그리기
        mc = mpf.make_marketcolors(up='r', down='b')  # 가격이 올랐을 때는 빨강, 내렸을 때는 파랑으로 설정
        s = mpf.make_mpf_style(marketcolors=mc)
        mpf.plot(df, type='candle', title=f'{selected_option} Chart', ylabel='Price', volume=True, style=s, datetime_format='%Y-%m-%d %H:%M:%S')









##########################################################################################################################################




    # Before 데이터 조회 및 차트 그리기
        # Between 데이터 조회 및 차트 그리기
    def query_data_before(self):
        selected_option = self.combo_box.currentText()  # 선택된 옵션 가져오기

        end_date_input = self.end_timestamp_edit.text().strip()

        # 값이 비어 있는지 확인
        if not end_date_input:
            self.msg_box.warning(self, "Error", "End Date를 입력하세요.")
            return

        # 입력된 날짜 문자열을 날짜 형식으로 변환
        try:
            end_date = datetime.strptime(end_date_input, "%Y-%m-%d").date()
        except ValueError:
            self.msg_box.warning(self, "Error", "올바른 날짜 형식(YYYY-MM-DD)으로 입력하세요.")
            return

        # SQL 쿼리(a <= x <= b) 실행
        query_before = f"SELECT * FROM {selected_option} WHERE date <= '{end_date}'"
        result = self.session.execute(query_before)


        row_list = list(result)

        modified_list = []  # row_list는 immutable 객체이므로 데이터를 담을 새로운 list 생성


        for row in row_list:
            timestamp = int(datetime.timestamp(row[0])) # DB table에 date를 timestamp로 변환
            datetime_obj = datetime.fromtimestamp(timestamp)

            # 튜플 언패킹으로 첫 번째 요소를 datetime_obj로 대체(timestamp를 datetime으로 변환한 것 + OHLCV + N_of_trades)
            modified_row = (datetime_obj,) + row[1:]
            modified_list.append(modified_row)
    
        # 결과 출력
        self.result_text.clear()
        self.result_text.append(f"데이터를 조회한 결과 총 {len(modified_list)}개의 데이터가 있습니다.")
        self.result_text.append("")
    
        if len(modified_list) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return
    
        for row in modified_list:
            datetime_str = row[0].strftime("%Y-%m-%d %H:%M:%S")  # 시간 형식 변경
            BTC_data = (datetime_str,) + row[1:]
            self.result_text.append(str(BTC_data))
    
        # DataFrame으로 변환
        df = pd.DataFrame(modified_list, columns=["Date", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["Date"])  # 인덱스를 datetime 형식으로 변환
        df.set_index("Date", inplace=True)
    
        if len(df) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return
    
        # 캔들 차트 그리기
        mc = mpf.make_marketcolors(up='r', down='b')  # 가격이 올랐을 때는 빨강, 내렸을 때는 파랑으로 설정
        s = mpf.make_mpf_style(marketcolors=mc)
        mpf.plot(df, type='candle', title=f'{selected_option} Chart', ylabel='Price', volume=True, style=s, datetime_format='%Y-%m-%d %H:%M:%S')





if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()