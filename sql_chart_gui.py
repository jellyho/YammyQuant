from data.readers import SQLReader
import mplfinance as mpf
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton, QLineEdit, QTextEdit, QMessageBox, QComboBox
from PyQt5.QtCore import Qt
from datetime import datetime


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.reader = SQLReader(host='jellyho.iptime.org', user='yammyquant', password='dialfl752', db='binance')
        self.reader.setTable('BTCUSDT', '1d')

        self.setWindowTitle("SQL Data Viewer")
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
        self.query_button1 = QPushButton("Load")
        self.query_button1.setToolTip("버튼을 눌러 데이터를 불러옵니다.")
        self.query_button1.clicked.connect(self.query_data_between)
        layout.addWidget(self.query_button1)
        self.query_button1.setStyleSheet(
            "QPushButton { background-color: white; color: black; border-radius: 8px; height: 20px;}")

        # ticker QComboBox 설정
        self.combo_box_ticker = QComboBox()
        self.combo_box_ticker.addItems(['BTCUSDT', 'ETHUSDT', 'XRPUSDT'])  # 필요한 옵션을 추가
        layout.addWidget(self.combo_box_ticker)

        # interval QComboBox 설정
        self.combo_box_interval = QComboBox()
        self.combo_box_interval.addItems(['1m', '5m', '15m', '1h', '6h', '1d', '1w'])  # 필요한 옵션을 추가
        layout.addWidget(self.combo_box_interval)

        # 결과 출력창
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        layout.addWidget(self.result_text)
        self.msg_box = QMessageBox(self)

    # Between 데이터 조회 및 차트 그리기
    def query_data_between(self):
        ticker = self.combo_box_ticker.currentText()  # 선택된 옵션 가져오기
        interval = self.combo_box_interval.currentText()  # 선택된 옵션 가져오기
        start_date_input = self.start_timestamp_edit.text()
        end_date_input = self.end_timestamp_edit.text()

        # 입력된 날짜 문자열을 datetime.datetime 형식으로 변환
        try:
            start_date = None if not start_date_input else datetime.strptime(start_date_input,'%Y-%m-%d %H:%M:%S')
            end_date = None if not end_date_input else datetime.strptime(end_date_input, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            self.msg_box.warning(self, "Error", "올바른 날짜 형식(YYYY-MM-DD HH:MM:SS)으로 입력하세요.")
            return

        # SQL 쿼리(a <= x <= b) 실행
        self.reader.setTable(ticker, interval)
        self.reader.setDate(start_date, end_date)
        candle = self.reader.read()

        # 결과 출력
        self.result_text.clear()
        self.result_text.append(f"데이터를 조회한 결과 총 {len(candle)}개의 데이터가 있습니다.")
        self.result_text.append("")

        if len(candle) == 0:  # 데이터가 없는 경우 처리
            self.result_text.append("데이터가 없습니다.")
            return

        # 캔들 차트 그리기
        mc = mpf.make_marketcolors(up='r', down='b')  # 가격이 올랐을 때는 빨강, 내렸을 때는 파랑으로 설정
        s = mpf.make_mpf_style(marketcolors=mc)
        mpf.plot(candle.data, type='candle', title=f'{ticker}-{interval} Chart', ylabel='Price', volume=True, style=s, datetime_format='%Y-%m-%d %H:%M:%S')


if __name__ == "__main__":
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()