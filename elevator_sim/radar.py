# -*- coding: utf-8 -*-
"""
毫米波雷达监测模块（阶段2）。

模拟安装在每个楼层电梯门前的毫米波雷达传感器：
    - 实时检测门前候梯区是否有人（存在性检测）；
    - 若某层有呼梯但门前持续无人超过阈值，自动取消该呼梯（按钮灭灯）；
    - 电梯即将到达（临近楼层锁定）时不取消，防止人刚走开又回来或检测抖动导致误取消。

与"乘客主动放弃"的区别：
    - 放弃（traffic.py）：乘客按完按钮主动离开，按钮仍亮，电梯会空停；
    - 雷达取消（radar.py）：传感器检测不到人，系统主动灭灯，电梯不再停靠。
    两者独立运作：放弃乘客走后雷达也会检测到无人，从而提前取消呼梯、避免空停。
"""

from typing import Dict, List, Set

import config


class FloorRadar:
    """单楼层门前雷达状态。"""

    def __init__(self, floor: int):
        self.floor = floor
        self.person_present: bool = False          # 当前是否检测到人
        self.empty_duration: int = 0               # 持续无人时长（秒）
        self.last_cancelled_dir: int = 0           # 最近一次被雷达取消的呼梯方向（1/-1/0）

    def update(self, present: bool) -> None:
        """更新一次采样结果。"""
        if present:
            self.person_present = True
            self.empty_duration = 0
        else:
            self.person_present = False
            self.empty_duration += 1

    def reset(self) -> None:
        self.person_present = False
        self.empty_duration = 0
        self.last_cancelled_dir = 0


class RadarSystem:
    """全楼层毫米波雷达管理系统。"""

    def __init__(self,
                 total_floors: int,
                 empty_cancel_seconds: int = config.RADAR_EMPTY_CANCEL_SECONDS,
                 near_floor_lock: int = config.RADAR_NEAR_FLOOR_LOCK,
                 enabled: bool = True):
        self.total_floors = total_floors
        self.empty_cancel_seconds = empty_cancel_seconds
        self.near_floor_lock = near_floor_lock
        self.enabled = enabled
        self.radars: Dict[int, FloorRadar] = {
            f: FloorRadar(f) for f in range(1, total_floors + 1)
        }
        # 统计：雷达自动取消的呼梯次数
        self.auto_cancel_count: int = 0

    # ---------------- 人员存在性模拟 ----------------
    def set_presence_from_passengers(self,
                                     waiting_origins: Dict[int, int]) -> None:
        """
        根据当前各楼层等待乘客数更新雷达检测结果。
        waiting_origins: {楼层: 该层等待乘客数}
        有人等待 -> 雷达检测到人；无人等待 -> 雷达检测不到人。
        （纯软件仿真：用等待乘客数模拟雷达的人体存在检测。）
        """
        for f, radar in self.radars.items():
            count = waiting_origins.get(f, 0)
            radar.update(count > 0)

    # ---------------- 呼梯自动取消判定 ----------------
    def check_auto_cancel(self,
                          hall_up: Set[int],
                          hall_down: Set[int],
                          elevator_floor: int,
                          elevator_direction: int) -> List[dict]:
        """
        检查所有有呼梯的楼层，若门前持续无人且电梯未临近，则自动取消呼梯。

        返回本次被取消的呼梯列表，每项为 {"floor": int, "direction": int}。
        调用方需据此从 hall_up / hall_down 中移除对应楼层。

        临近楼层锁定：电梯与呼梯楼层的距离 <= near_floor_lock 时，
        即使门前无人也不取消（人可能刚走开半步、或检测抖动）。
        """
        if not self.enabled:
            return []
        cancelled: List[dict] = []

        for floor in sorted(hall_up | hall_down):
            radar = self.radars[floor]
            # 门前有人 -> 不取消
            if radar.person_present:
                continue
            # 持续无人未达阈值 -> 不取消
            if radar.empty_duration < self.empty_cancel_seconds:
                continue
            # 电梯临近该楼层 -> 锁定，不取消
            distance = abs(elevator_floor - floor)
            if distance <= self.near_floor_lock:
                continue

            # 满足条件，取消该层所有未消号呼梯
            if floor in hall_up:
                cancelled.append({"floor": floor, "direction": 1})
                radar.last_cancelled_dir = 1
                self.auto_cancel_count += 1
            if floor in hall_down:
                cancelled.append({"floor": floor, "direction": -1})
                radar.last_cancelled_dir = -1
                self.auto_cancel_count += 1
            # 取消后重置无人计时，避免重复触发
            radar.empty_duration = 0

        return cancelled

    # ---------------- 查询接口（可视化用） ----------------
    def get_radar_state(self, floor: int) -> dict:
        """返回某层雷达状态，供GUI绘制。"""
        r = self.radars.get(floor)
        if r is None:
            return {"present": False, "empty_duration": 0, "cancelled": False}
        return {
            "present": r.person_present,
            "empty_duration": r.empty_duration,
            "empty_seconds": self.empty_cancel_seconds,
            "cancelled": r.last_cancelled_dir != 0,
        }

    def reset(self) -> None:
        for r in self.radars.values():
            r.reset()
        self.auto_cancel_count = 0
