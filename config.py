# -*- coding: utf-8 -*-
"""
项目全局配置文件（阶段1：基础电梯运行仿真）
所有可调参数集中在这里，后续阶段新增的雷达阈值、载重阈值、防夹参数等
也会统一追加到本文件，无需修改业务代码。
"""

# ==================== 电梯基础参数 ====================
TOTAL_FLOORS = 10              # 总楼层数（楼层编号 1 ~ TOTAL_FLOORS）
RATED_LOAD_KG = 1000           # 额定载重（kg），阶段1仅定义，阶段3载重检测启用
PERSON_WEIGHT_KG = 75          # 单名乘客平均体重（kg），阶段3使用

# 各动作耗时（单位：仿真秒，每个 tick = 1 秒）
TRAVEL_TIME_PER_FLOOR = 2      # 电梯运行一层楼所需时间
DOOR_OPEN_TIME = 2             # 开门动作耗时
DOOR_HOLD_TIME = 5             # 开门后保持时间（供乘客进出）
DOOR_CLOSE_TIME = 2            # 关门动作耗时

# ==================== 仿真参数 ====================
SIMULATION_DURATION = 600      # 客流生成持续时长（秒）；之后只服务不再产生新乘客
RANDOM_SEED = 42               # 随机种子，保证每次运行结果可复现
PRINT_TICK_LOG = False         # 是否打印每个 tick 的详细状态（调试用）
PRINT_EVENT_LOG = True         # 是否打印事件日志（呼梯、到站、放弃、完成）

# ==================== 客流参数 ====================
CALL_ARRIVAL_RATE = 0.15       # 每个 tick 产生一名新乘客的概率
ABANDON_PROBABILITY = 0.20     # 乘客呼梯后"按完就走"放弃乘梯的概率
ABANDON_MIN_WAIT = 5           # 放弃者最短等待时间（秒）
ABANDON_MAX_WAIT = 20          # 放弃者最长等待时间（秒）

# 客流方向分布（符合真实楼宇：大部分人下楼到1层，少部分上楼或中间往返）
# 三项之和必须为 1.0
TRAFFIC_DOWN_TO_1F = 0.55      # 从任意楼层(2~10)下行到1层（回家/下班）
TRAFFIC_UP_FROM_1F = 0.25      # 从1层上行到任意楼层(2~10)（上楼/上班）
TRAFFIC_MID_FLOOR = 0.20       # 中间楼层之间往返（2~10层互达）

# ==================== 阶段2：毫米波雷达监测 ====================
RADAR_DETECTION_RANGE_M = 3.0  # 雷达有效检测距离（米），覆盖门前候梯区
RADAR_EMPTY_CANCEL_SECONDS = 8 # 门前持续无人多少秒后自动取消呼梯
RADAR_NEAR_FLOOR_LOCK = 2      # 电梯距目标楼层≤N层时锁定呼梯，不取消（防止误取消）
RADAR_SAMPLE_INTERVAL = 1      # 雷达采样间隔（仿真秒），每tick检测一次

# ==================== 阶段3：轿厢负重检测 ====================
LOAD_CELL_SAMPLE_INTERVAL = 1  # 负重采样间隔（仿真秒），每tick更新一次
OVERLOAD_ALARM_DELAY = 0       # 超载后立即报警（秒），0=立即
OVERLOAD_HOLD_DOOR_OPEN = True # 超载时保持门打开，不允许关门运行

# ==================== 阶段4：关门防夹保护 ====================
ANTI_PINCH_ENABLED = True       # 是否启用关门防夹保护
ANTI_PINCH_DETECTION_RANGE_M = 1.5  # 防夹检测距离（米），门前区域
ANTI_PINCH_REOPEN_DELAY = 0     # 检测到闯入后立即重开（秒），0=立即
# 闯入判定：关门开始后门前等待人数增加量超过此值即判定有人闯入
ANTI_PINCH_PERSON_THRESHOLD = 1
# 关门过程中每tick出现"未按按钮的门前行人"的概率
# 0=禁用（默认，避免干扰基础调度测试），实验/GUI演示时可调到0.1~0.2
ANTI_PINCH_PEDESTRIAN_PROB = 0.0
# 行人初始距离门口的步数（越大走得越久，动画越明显）
# 关门时间=2秒，所以设为2步确保关门期间能走到门口触发防夹
ANTI_PINCH_PEDESTRIAN_START_DISTANCE = 2
# 行人每tick靠近的步数
ANTI_PINCH_PEDESTRIAN_SPEED = 1
