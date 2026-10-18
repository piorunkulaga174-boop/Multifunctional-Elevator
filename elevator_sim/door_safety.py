# -*- coding: utf-8 -*-
"""
关门防夹保护模块（阶段4，行人接近动画版）。

模拟电梯门上的安全触板/红外对射/毫米波雷达：
    - 关门过程中实时监测门前区域是否有人接近；
    - 行人从远处出现，逐步走向电梯门；
    - 行人到达门口时立即停止关门并重新开门，防止夹人；
    - 门完全关闭后不再检测（已安全关闭）。

闯入判定逻辑（纯软件仿真）：
    1. 等待人数增加：关门开始后门前等待乘客数增加（有人新按呼梯）；
    2. 行人到达门口：关门过程中有人走向电梯并到达门口（未按按钮）；
    以上任一情况即判定为闯入，立即重开。

与阶段2雷达的区别：
    - 阶段2雷达：检测门前是否有人，用于无人呼梯自动取消（长时间尺度）；
    - 阶段4防夹：检测关门过程中是否有人闯入（短时间尺度，即时响应）。
"""

import random
from typing import Dict, List, Optional

import config
from .passenger import Passenger, PassengerStatus


class Pedestrian:
    """
    门前行人（未按按钮，正在走向电梯）。
    distance 表示距离门口的步数，从初始值逐步减少到0（到达门口）。
    """
    def __init__(self, start_distance: int = 5):
        self.distance = start_distance
        self.start_distance = start_distance

    def step_closer(self, speed: int = 1) -> None:
        """每tick靠近一步。"""
        self.distance = max(0, self.distance - speed)

    @property
    def at_door(self) -> bool:
        """是否已到达门口。"""
        return self.distance <= 0

    @property
    def progress(self) -> float:
        """接近进度 0~1，用于GUI动画（0=刚出现，1=到门口）。"""
        if self.start_distance <= 0:
            return 1.0
        return 1.0 - (self.distance / self.start_distance)


class DoorSafetySystem:
    """电梯门安全防护系统。"""

    def __init__(self,
                 enabled: bool = config.ANTI_PINCH_ENABLED,
                 person_threshold: int = config.ANTI_PINCH_PERSON_THRESHOLD,
                 pedestrian_prob: float = config.ANTI_PINCH_PEDESTRIAN_PROB,
                 pedestrian_start_distance: int = config.ANTI_PINCH_PEDESTRIAN_START_DISTANCE,
                 pedestrian_speed: int = config.ANTI_PINCH_PEDESTRIAN_SPEED):
        self.enabled = enabled
        self.person_threshold = person_threshold
        # 关门过程中每tick出现新行人的概率
        self.pedestrian_prob = pedestrian_prob
        # 行人初始距离门口的步数（越大走得越久）
        self.pedestrian_start_distance = pedestrian_start_distance
        # 行人每tick靠近的步数
        self.pedestrian_speed = pedestrian_speed
        # 关门开始时各层门前等待人数（用于对比判断是否有人按呼梯闯入）
        self._waiting_at_closing: Dict[int, int] = {}
        # 当前各层门前的行人列表（正在接近的人）
        self._pedestrians: Dict[int, List[Pedestrian]] = {}
        # 统计：防夹重开次数
        self.reopen_count: int = 0
        # 最近一次防夹触发的楼层（供GUI显示）
        self.last_reopen_floor: Optional[int] = None
        # 供仿真器使用的随机数生成器（与主仿真独立，避免干扰客流）
        self._rng = random.Random(999)

    def on_door_closing(self, floor: int, waiting_count: int) -> None:
        """
        门开始关闭时调用，记录当前层门前等待人数。
        同时清除该层之前的行人记录。
        """
        self._waiting_at_closing[floor] = waiting_count
        self._pedestrians[floor] = []

    def update_pedestrians(self, floor: int) -> int:
        """
        关门过程中每tick调用：
        1. 有概率生成新行人（从远处出现）；
        2. 现有行人每tick靠近一步。
        返回当前层正在接近的行人数。
        """
        if not self.enabled:
            return 0
        peds = self._pedestrians.setdefault(floor, [])
        # 生成新行人（从远处出现）
        if self._rng.random() < self.pedestrian_prob:
            peds.append(Pedestrian(start_distance=self.pedestrian_start_distance))
        # 现有行人靠近
        for p in peds:
            p.step_closer(self.pedestrian_speed)
        return len(peds)

    def check_intrusion(self, floor: int, current_waiting: int) -> bool:
        """
        关门过程中调用，检测是否有人闯入。
        返回 True 表示检测到闯入，应立即重开门。

        闯入条件（任一满足）：
        1. 等待人数增加 -> 有人新按呼梯；
        2. 有行人到达门口 -> 有人走向电梯并到达门口。
        """
        if not self.enabled:
            return False
        baseline = self._waiting_at_closing.get(floor, 0)
        # 条件1：等待人数增加（有人新按呼梯）
        increase = current_waiting - baseline
        if increase >= self.person_threshold:
            return True
        # 条件2：有行人到达门口
        peds = self._pedestrians.get(floor, [])
        if any(p.at_door for p in peds):
            return True
        return False

    def trigger_reopen(self, floor: int) -> None:
        """记录一次防夹重开。"""
        self.reopen_count += 1
        self.last_reopen_floor = floor

    def consume_pedestrians(self, floor: int) -> int:
        """
        防夹重开后，将门前的行人转化为等待乘客（他们会按呼梯并进入）。
        返回转化的行人数。
        """
        peds = self._pedestrians.get(floor, [])
        count = len(peds)
        self._pedestrians[floor] = []
        return count

    def get_waiting_count(self, passengers: List[Passenger], floor: int) -> int:
        """统计指定楼层门前等待的乘客数。"""
        return sum(1 for p in passengers
                   if p.status == PassengerStatus.WAITING and p.origin == floor)

    def get_pedestrian_count(self, floor: int) -> int:
        """获取指定楼层当前正在接近的行人数。"""
        return len(self._pedestrians.get(floor, []))

    def get_pedestrians(self, floor: int) -> List[Pedestrian]:
        """获取指定楼层的行人列表（供GUI显示位置）。"""
        return self._pedestrians.get(floor, [])

    def reset(self) -> None:
        self._waiting_at_closing.clear()
        self._pedestrians.clear()
        self.reopen_count = 0
        self.last_reopen_floor = None
