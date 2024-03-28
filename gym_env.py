import random
from datetime import datetime, timedelta
import gym, cv2
from gym import spaces
import numpy as np
import matplotlib.pyplot as plt
from data.readers import BinanceReader


class ChartFollowing(gym.Env):
    """
    강화학습 환경에 대한 설명을 여기에 작성합니다.
    """

    def __init__(self):
        # 액션 공간 정의
        self.action_space = spaces.Box(low=-2.0, high=2.0, shape=(1,), dtype=np.float32)
        
        # 상태 공간 정의
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(11,), dtype=np.float32)
        
        # 환경 초기화
        self.state = None
        self.position = 0
        self.position_history = []
        self.next_position_history = []
        self.next_position = 0
        self.index = 11
        self.len = 0
        self.current_distribution = (0, 0)
        self.reader = BinanceReader()
        self.reader.setTicker('BTCUSDT')
        self.reader.setInterval('5m')
        self.reset()

    def step(self, action):
        """
        환경에서 액션을 취하고, 다음 상태, 보상, 종료 여부, 추가 정보를 반환합니다.
        
        Args:
            action (ndarray): 에이전트가 취한 액션
            
        Returns:
            observation (ndarray): 새로운 상태
            reward (float): 보상
            done (bool): 에피소드가 종료되었는지 여부
            info (dict): 디버깅을 위한 추가 정보
        """
        
        # 상태 전이 로직
        self.position += action[0] * self.current_distribution[1]
        self.position_history.append(self.position)
        self.next_position_history.append(self.next_position)

        # 보상 계산 로직
        reward = -np.abs(self.next_position - self.position) / self.current_distribution[1]
        
        done = False
        # 종료 조건 확인
        if self.index > self.len - 3:
            done = True
        else:
            done = False
        
        info = {}
        self.index += 1
        self._preprocessing()
        observation = self.state

        return observation, reward, done, info

    def reset(self):
        """
        환경을 초기화하고 초기 상태를 반환합니다.
        
        Returns:
            observation (ndarray): 초기 상태
        """
        start, end = self._random_date_generator()
        self.reader.setDate(start, end)
        self.close = self.reader.read().close
        self.index = 11
        self.len = len(self.close)
        self.position_history = []
        self.next_position_history = []
        self._preprocessing(True)
        return self.state

    def render(self, mode='human'):
        """
        환경을 시각화합니다. (선택 사항)
        """
        title = "ChartFollowing"
        window_size = (720, 480)
        norm = np.min([np.min(self.position_history), np.min(self.next_position_history)]), np.max([np.max(self.position_history), np.max(self.next_position_history)])
        ref = (self.next_position_history - norm[0]) / (norm[1] - norm[0])  # 정규화
        trj = (self.position_history - norm[0]) / (norm[1] - norm[0])  # 정규화
        ref = ref * (window_size[1] - 50)  # 창 높이에 맞게 스케일링
        ref = ref.astype(np.int32)
        trj = trj * (window_size[1] - 50)  # 창 높이에 맞게 스케일링
        trj = trj.astype(np.int32)
        
        # 창 생성
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(title, window_size[0], window_size[1])
        background = np.ones((window_size[1], window_size[0], 3), dtype=np.uint8) * 255
        gap = int(window_size[0] / len(ref))
        # 그래프 그리기
        for i in range(1, len(ref)):
            cv2.line(background, ((i-1)*gap, window_size[1] - ref[i-1] - 25), (i*gap, window_size[1] - ref[i] - 25), (0, 255, 0), 1)
        for i in range(1, len(trj)):
            cv2.line(background, ((i-1)*gap, window_size[1] - trj[i-1] - 25), (i*gap, window_size[1] - trj[i] - 25), (0, 0, 255), 1)
        
        # 창 표시
        cv2.imshow(title, background)
        
        # 'q' 키를 누르면 종료
        if cv2.waitKey(1) & 0xFF == ord('q'):
            pass

    def _preprocessing(self, first=False):
        cl = self.close[self.index - 11 : self.index]
        self.current_distribution = cl[:-1].mean(), cl[:-1].std()+0.0001
        if first:
            self.position = cl[-2]
        self.next_position = cl[-1]
        cl = (cl - self.current_distribution[0]) / self.current_distribution[1]
        self.state = np.concatenate([cl[:-1], [(self.position - self.current_distribution[0]) / self.current_distribution[1]]])


    def _random_date_generator(self, start_date="2017-08-18", end_date="2023-12-31"):
        """
        start_date와 end_date 사이의 날짜를 랜덤으로 샘플링하는 함수
        
        Args:
            start_date (str): 시작 날짜 (YYYY-MM-DD)
            end_date (str): 종료 날짜 (YYYY-MM-DD)
            
        Returns:
            str: 랜덤으로 샘플링된 날짜 (YYYY-MM-DD HH:MM:SS)
        """
        start_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date = datetime.strptime(end_date, "%Y-%m-%d")
        
        # 시작 날짜와 종료 날짜 사이의 날짜 수
        days_between = (end_date - start_date).days
        
        # 랜덤으로 날짜 선택
        random_days = random.randint(0, days_between)
        random_date_start = start_date + timedelta(days=random_days)
        random_date_end = start_date + timedelta(days=random_days+1)
        
        # 시간 추가 (00:00:00)
        random_date_start = random_date_start.strftime("%Y-%m-%d 00:00:00")
        random_date_end = random_date_end.strftime("%Y-%m-%d 00:00:00")
        
        return random_date_start, random_date_end

if __name__ == '__main__':
    # 환경 인스턴스 생성
    env = ChartFollowing()
    
    # 환경 테스트
  
    while True:
        observation = env.reset()
        done = False
        while not done:
            # 랜덤 액션 선택 (예시)
            action = env.action_space.sample()
            
            # 액션 취하고 다음 상태 관측
            observation, reward, done, info = env.step(action)
            env.render()
        print("Episode finished!")