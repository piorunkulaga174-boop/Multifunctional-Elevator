# -*- coding: utf-8 -*-
"""
轿厢负重检测模块（阶段3）。

模拟安装在轿厢底部的称重传感器（load cell）：
    - 实时监测轿厢内当前载重（kg）；
    - 载重达到或超过额定载重时判定为超载；
    - 超载时触发报警，电梯保持开门、不允许新乘客进入、不关门运行；
    - 乘客出厢后载重降低，低于额定载重时自动解除超载。

纯软件仿真：用"轿厢内乘客数 × 单人均重"模拟称重传感器读数。
"""

from typing import List

import config
from .passenger import Passenger, PassengerStatus


class LoadCell:
    """轿厢负重传感器。"""

    def __init__(self,
                 rated_load_kg: float = config.RATED_LOAD_KG,
                 person_weight_kg: float = config.PERSON_WEIGHT_KG,
                 enabled: bool = True):
        self.rated_load_kg = rated_load_kg
        self.person_weight_kg = person_weight_kg
        self.enabled = enabled
        self.current_load_kg: float = 0.0
        self.overload: bool = False
        # 统计：超载发生次数、累计超载持续时间（秒）
        self.overload_count: int = 0
        self.overload_duration: int = 0
        self._was_overload: bool = False

    def update_from_passengers(self, passengers: List[Passenger]) -> None:
        """
        根据当前轿厢内乘客列表更新载重。
        轿厢内乘客 = 状态为 IN_CAR 的乘客。
        """
        in_car = [p for p in passengers if p.status == PassengerStatus.IN_CAR]
        self.current_load_kg = len(in_car) * self.person_weight_kg
        # 禁用时不判定超载
        self.overload = self.enabled and (self.current_load_kg >= self.rated_load_kg)

        # 统计超载次数（上升沿计数）和持续时间
        if self.overload and not self._was_overload:
            self.overload_count += 1
        if self.overload:
            self.overload_duration += 1
        self._was_overload = self.overload

    def can_accept(self, additional_weight_kg: float = None) -> bool:
        """
        判断是否还能再进入一名乘客。
        additional_weight_kg 默认为单人均重。
        允许载重达到额定值（达到即判定为超载），超过则拒绝。
        禁用时始终返回True（不限制进入）。
        """
        if not self.enabled:
            return True
        if additional_weight_kg is None:
            additional_weight_kg = self.person_weight_kg
        return (self.current_load_kg + additional_weight_kg) <= self.rated_load_kg

    @property
    def load_ratio(self) -> float:
        """当前载重 / 额定载重（0.0 ~ 1.0+）。"""
        return self.current_load_kg / self.rated_load_kg if self.rated_load_kg else 0.0

    @property
    def remaining_capacity_kg(self) -> float:
        """剩余载重容量（kg），超载时为0或负数。"""
        return self.rated_load_kg - self.current_load_kg

    def reset(self) -> None:
        self.current_load_kg = 0.0
        self.overload = False
        self.overload_count = 0
        self.overload_duration = 0
        self._was_overload = False
