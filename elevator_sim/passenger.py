# -*- coding: utf-8 -*-
"""
乘客与乘梯状态定义。
一名乘客代表一次完整的乘梯需求：在起点层呼梯 -> 等待 -> 进入轿厢 -> 到达目标层。
"""

import enum
from dataclasses import dataclass
from typing import Optional


class PassengerStatus(enum.Enum):
    """乘客生命周期状态。"""
    WAITING = "waiting"        # 正在厅外等待电梯
    ABANDONED = "abandoned"    # 呼梯后放弃乘梯离开（按钮仍亮，会造成空停）
    IN_CAR = "in_car"          # 已进入轿厢
    DONE = "done"              # 已到达目标层，行程结束


@dataclass
class Passenger:
    """单名乘客。"""
    pid: int                              # 乘客编号
    origin: int                           # 呼梯（起点）楼层
    target: int                           # 目标楼层
    call_time: int                        # 呼梯时刻（仿真秒）
    direction: int                        # 呼梯方向：1=上行，-1=下行
    abandon_time: Optional[int] = None    # 放弃离开的时刻；None 表示不会放弃
    board_time: Optional[int] = None      # 进入轿厢的时刻
    arrive_time: Optional[int] = None     # 到达目标层的时刻
    status: PassengerStatus = PassengerStatus.WAITING

    @property
    def wait_time(self) -> Optional[int]:
        """成功乘梯时的等待时间（呼梯 -> 进轿厢）。"""
        if self.board_time is not None:
            return self.board_time - self.call_time
        return None

    @property
    def travel_time(self) -> Optional[int]:
        """整段行程耗时（呼梯 -> 到达目标层）。"""
        if self.arrive_time is not None:
            return self.arrive_time - self.call_time
        return None
