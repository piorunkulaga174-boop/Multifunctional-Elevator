# -*- coding: utf-8 -*-
"""
随机客流生成器（阶段1）。
按概率在随机楼层产生乘客；部分乘客会在等待一段时间后放弃乘梯（"按完就走"），
用于复现无效呼梯与空停场景，为阶段2的雷达监测提供对照数据。
"""

import random
from typing import List, Tuple

import config
from .passenger import Passenger, PassengerStatus


class TrafficGenerator:
    def __init__(self,
                 total_floors: int,
                 arrival_rate: float,
                 abandon_probability: float,
                 abandon_min_wait: int,
                 abandon_max_wait: int,
                 rng: random.Random,
                 down_to_1f: float = config.TRAFFIC_DOWN_TO_1F,
                 up_from_1f: float = config.TRAFFIC_UP_FROM_1F,
                 mid_floor: float = config.TRAFFIC_MID_FLOOR):
        self.total_floors = total_floors
        self.arrival_rate = arrival_rate
        self.abandon_probability = abandon_probability
        self.abandon_min_wait = abandon_min_wait
        self.abandon_max_wait = abandon_max_wait
        self.rng = rng
        self._next_pid = 1
        # 客流方向分布（真实楼宇：大部分下楼到1层）
        self.down_to_1f = down_to_1f
        self.up_from_1f = up_from_1f
        self.mid_floor = mid_floor

    def _pick_origin_target(self) -> Tuple[int, int, int]:
        """
        按真实客流分布生成（起点, 目标, 方向）。
        - 55%: 从2~10层下行到1层（回家/下班）
        - 25%: 从1层上行到2~10层（上楼/上班）
        - 20%: 中间楼层之间往返
        """
        r = self.rng.random()
        if r < self.down_to_1f:
            # 下行到1层
            origin = self.rng.randint(2, self.total_floors)
            target = 1
            direction = -1
        elif r < self.down_to_1f + self.up_from_1f:
            # 从1层上行
            origin = 1
            target = self.rng.randint(2, self.total_floors)
            direction = 1
        else:
            # 中间楼层往返（起点和目标都在2~10层，且不同）
            origin = self.rng.randint(2, self.total_floors)
            target = self.rng.randint(2, self.total_floors - 1)
            if target >= origin:
                target += 1
            direction = 1 if target > origin else -1
        return origin, target, direction

    def maybe_generate(self, now: int) -> List[Passenger]:
        """每个 tick 调用，按概率返回 0 或 1 名新乘客。"""
        if self.rng.random() >= self.arrival_rate:
            return []
        origin, target, direction = self._pick_origin_target()

        abandon_time = None
        if self.rng.random() < self.abandon_probability:
            abandon_time = now + self.rng.randint(self.abandon_min_wait,
                                                  self.abandon_max_wait)
        passenger = Passenger(
            pid=self._next_pid,
            origin=origin,
            target=target,
            call_time=now,
            direction=direction,
            abandon_time=abandon_time,
        )
        self._next_pid += 1
        return [passenger]

    def update_abandonment(self, passengers: List[Passenger], now: int) -> List[Passenger]:
        """
        更新等待中乘客的放弃状态。
        返回本 tick 新放弃的乘客列表（注意：放弃后厅外按钮仍保持亮灯）。
        """
        newly_abandoned = []
        for p in passengers:
            if p.status == PassengerStatus.WAITING \
                    and p.abandon_time is not None and now >= p.abandon_time:
                p.status = PassengerStatus.ABANDONED
                newly_abandoned.append(p)
        return newly_abandoned
