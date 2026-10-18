# -*- coding: utf-8 -*-
"""
电梯核心状态机（阶段1）。

状态流转：
    IDLE（待机）
      └─ 收到呼梯 -> MOVING_UP / MOVING_DOWN（运行）
                        └─ 到达需停靠楼层 -> OPENING（开门）
                                              └─ OPEN（保持，乘客进出）
                                                    └─ CLOSING（关门）
                                                          ├─ 还有请求 -> MOVING_UP / MOVING_DOWN
                                                          └─ 无请求   -> IDLE
    FAULT（故障）：阶段1仅预留，阶段5异常场景启用。

调度规则：标准集选（SCAN）
    电梯保持当前运行方向，依次服务同方向请求；
    当前方向上再无任何请求时换向，所有请求服务完后回到待机。
"""

import enum
from typing import List, Optional, Set


class ElevatorState(enum.Enum):
    """电梯运行状态。"""
    IDLE = "idle"               # 待机
    MOVING_UP = "moving_up"     # 上行
    MOVING_DOWN = "moving_down"  # 下行
    OPENING = "opening"         # 开门动作中
    OPEN = "open"               # 门保持打开（乘客进出）
    CLOSING = "closing"         # 关门动作中
    FAULT = "fault"             # 故障（预留）


class Elevator:
    """单台电梯。"""

    def __init__(self,
                 total_floors: int,
                 travel_time_per_floor: int,
                 door_open_time: int,
                 door_hold_time: int,
                 door_close_time: int):
        self.total_floors = total_floors
        self.travel_time = travel_time_per_floor
        self.door_open_time = door_open_time
        self.door_hold_time = door_hold_time
        self.door_close_time = door_close_time

        # ---- 运行状态 ----
        self.state: ElevatorState = ElevatorState.IDLE
        self.current_floor: int = 1          # 轿厢当前所在楼层
        self.direction: int = 1              # 当前运行方向：1=上行，-1=下行

        # ---- 阶段3：超载标志（由仿真器根据负重传感器设置） ----
        # True 时：开门保持状态不计时、不关门，直到超载解除
        self.overload: bool = False
        # ---- 阶段4修复：开门延长机制 ----
        # 仿真器可调用 extend_hold() 延长开门时间（有新乘客来时）
        # 最长开门时间限制，防止门永远关不上
        self.max_hold_time: int = 30
        self._total_open_time: int = 0

        # ---- 请求集合 ----
        # 厅外呼梯：元素为楼层号，分别记录上行 / 下行按钮
        self.hall_up: Set[int] = set()
        self.hall_down: Set[int] = set()
        # 轿内选层：乘客进入后登记的目标楼层
        self.car_calls: Set[int] = set()

        # ---- 计时器 ----
        self._action_timer: int = 0          # 当前动作（移动/开关门）已用时间
        self._hold_timer: int = 0            # 开门保持计时
        # 关门开始时本层仍存在的呼梯方向（本次停靠不服务的反向呼梯），
        # 用于区分"关门期间新按下的呼梯"，新呼梯应立即重新开门
        self._hall_up_at_closing: bool = False
        self._hall_down_at_closing: bool = False

        # ---- 统计原始计数（由仿真器进一步加工） ----
        self.stop_count: int = 0             # 总停站次数（每次开门计一次）

    # ==================== 请求登记 ====================
    def add_hall_call(self, floor: int, direction: int) -> None:
        """登记一次厅外呼梯（按钮亮灯）。"""
        if direction >= 0:
            self.hall_up.add(floor)
        else:
            self.hall_down.add(floor)

    def add_car_call(self, floor: int) -> None:
        """登记一次轿内选层。"""
        self.car_calls.add(floor)

    def clear_hall_calls(self, floor: int) -> None:
        """电梯停靠后清除该层的厅外呼梯（按钮消号）。"""
        self.hall_up.discard(floor)
        self.hall_down.discard(floor)

    # ==================== 调度判定 ====================
    def _has_request_above(self, floor: int) -> bool:
        """floor 层以上（不含本层）是否还有任何请求。"""
        return any(f > floor for f in self.hall_up | self.hall_down | self.car_calls)

    def _has_request_below(self, floor: int) -> bool:
        """floor 层以下（不含本层）是否还有任何请求。"""
        return any(f < floor for f in self.hall_up | self.hall_down | self.car_calls)

    def _all_requests(self) -> Set[int]:
        return self.hall_up | self.hall_down | self.car_calls

    def _should_stop(self, floor: int) -> bool:
        """到达 floor 层时，依据集选规则判断是否需要停靠。"""
        # 轿内选层一定停
        if floor in self.car_calls:
            return True
        if self.direction == 1:
            # 上行：同方向（上行）呼梯必停；
            # 反方向（下行）呼梯仅当上方已无任何请求时才停（顺带服务）
            if floor in self.hall_up:
                return True
            if floor in self.hall_down and not self._has_request_above(floor):
                return True
        else:
            # 下行：对称逻辑
            if floor in self.hall_down:
                return True
            if floor in self.hall_up and not self._has_request_below(floor):
                return True
        return False

    def _next_idle_target(self) -> Optional[int]:
        """待机时选取最早需要服务的请求楼层（取离轿厢最近的一个）。"""
        if not self._all_requests():
            return None
        return min(self._all_requests(), key=lambda f: (abs(f - self.current_floor), f))

    # ==================== 状态机推进（每个 tick 调用一次） ====================
    def tick(self) -> Optional[str]:
        """
        推进 1 秒。
        返回值：本 tick 发生的事件类型字符串（供仿真器处理乘客上下车），无事件为 None。
          - "arrived_open"：本 tick 刚完成开门、门已完全打开，应执行乘客进出
          - "doors_closed"：本 tick 刚完成关门，进入下一步移动/待机
        """
        event: Optional[str] = None

        if self.state == ElevatorState.FAULT:
            return None

        elif self.state == ElevatorState.IDLE:
            target = self._next_idle_target()
            if target is not None:
                if target > self.current_floor:
                    self.direction = 1
                    self.state = ElevatorState.MOVING_UP
                elif target < self.current_floor:
                    self.direction = -1
                    self.state = ElevatorState.MOVING_DOWN
                else:
                    # 请求就在本层，直接开门
                    self.state = ElevatorState.OPENING
                    self._action_timer = 0

        elif self.state in (ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN):
            self._action_timer += 1
            if self._action_timer >= self.travel_time:
                # 到达相邻楼层
                self.current_floor += 1 if self.state == ElevatorState.MOVING_UP else -1
                self._action_timer = 0
                if self._should_stop(self.current_floor):
                    self.state = ElevatorState.OPENING
                    self._action_timer = 0
                else:
                    # 继续运行；当前方向已无请求时换向或待机
                    self._maybe_reverse_or_idle()

        elif self.state == ElevatorState.OPENING:
            self._action_timer += 1
            if self._action_timer >= self.door_open_time:
                self._action_timer = 0
                self._hold_timer = 0
                self.state = ElevatorState.OPEN
                self.stop_count += 1
                event = "arrived_open"

        elif self.state == ElevatorState.OPEN:
            # 乘客进出由仿真器在事件后处理；门保持固定时间
            # 阶段3：超载时保持开门，不计时、不关门
            # 阶段4修复：开门延长机制——仿真器可调用 extend_hold() 重置计时
            if self.overload:
                pass
            else:
                self._hold_timer += 1
                self._total_open_time += 1
                # 超过最长开门时间则强制关门（防止门永远关不上）
                if self._total_open_time >= self.max_hold_time:
                    self._close_door()
                # 正常关门：保持时间到
                elif self._hold_timer >= self.door_hold_time:
                    self._close_door()

        elif self.state == ElevatorState.CLOSING:
            self._action_timer += 1
            if self._action_timer >= self.door_close_time:
                self._action_timer = 0
                event = "doors_closed"
                self._resume_service()

        return event

    def served_directions_at_stop(self) -> List[int]:
        """
        开门瞬间调用：依据集选规则返回本次停靠实际服务的厅外呼梯方向
        （1=上行，-1=下行），仿真器据此放对应方向的乘客进入并消号。
        """
        floor = self.current_floor
        served: List[int] = []
        if self.direction == 1:
            if floor in self.hall_up:
                served.append(1)
            # 上方已无任何请求时，顺带服务本层下行呼梯
            if floor in self.hall_down and not self._has_request_above(floor):
                served.append(-1)
        else:
            if floor in self.hall_down:
                served.append(-1)
            # 下方已无任何请求时，顺带服务本层上行呼梯
            if floor in self.hall_up and not self._has_request_below(floor):
                served.append(1)
        return served

    def _maybe_reverse_or_idle(self) -> None:
        """越过目标后若当前方向无请求，则换向或待机。"""
        if not self._all_requests():
            self.state = ElevatorState.IDLE
            return
        if self.direction == 1 and not self._has_request_above(self.current_floor - 1):
            # 上方无请求：若下方有请求则换向
            if self._has_request_below(self.current_floor + 1):
                self.direction = -1
                self.state = ElevatorState.MOVING_DOWN
        elif self.direction == -1 and not self._has_request_below(self.current_floor + 1):
            if self._has_request_above(self.current_floor - 1):
                self.direction = 1
                self.state = ElevatorState.MOVING_UP

    def _decide_next_direction(self, floor: int) -> Optional[int]:
        """
        关门后决定下一步运行方向。
        优先依据轿厢内目标（已进厢的乘客必须送达）；
        轿厢无目标时再依据厅外呼梯分布；都没有返回 None（待机）。
        """
        if not self._all_requests():
            return None
        car_above = any(f > floor for f in self.car_calls)
        car_below = any(f < floor for f in self.car_calls)
        if car_above and not car_below:
            return 1
        if car_below and not car_above:
            return -1
        if car_above and car_below:
            return self.direction          # 上下都有目标，保持当前方向
        # 轿厢为空，看厅外呼梯
        hall_above = any(f > floor for f in self.hall_up | self.hall_down)
        hall_below = any(f < floor for f in self.hall_up | self.hall_down)
        if hall_above and not hall_below:
            return 1
        if hall_below and not hall_above:
            return -1
        if hall_above and hall_below:
            return self.direction
        # 只剩本层呼梯
        if floor in self.hall_up:
            return 1
        if floor in self.hall_down:
            return -1
        return self.direction

    def _resume_service(self) -> None:
        """关门后决定下一步：重新开门（顺路的新呼梯）、继续移动或待机。"""
        floor = self.current_floor
        new_up = (floor in self.hall_up) and not self._hall_up_at_closing
        new_down = (floor in self.hall_down) and not self._hall_down_at_closing
        next_dir = self._decide_next_direction(floor)
        if next_dir is None:
            self.state = ElevatorState.IDLE
            return
        # 关门期间本层出现与下一步方向一致的新呼梯 -> 立即重新开门
        if (new_up and next_dir == 1) or (new_down and next_dir == -1):
            self.direction = next_dir
            self.state = ElevatorState.OPENING
            self._action_timer = 0
            return
        # 反向新呼梯不顺路，登记后正常启动，后续顺路再服务
        self.direction = next_dir
        self.state = (ElevatorState.MOVING_UP if next_dir == 1
                      else ElevatorState.MOVING_DOWN)

    # ==================== 阶段4：防夹重开 ====================
    def request_reopen(self) -> bool:
        """
        关门过程中请求重新开门（防夹保护触发）。
        仅在 CLOSING 状态下有效，返回是否成功触发重开。
        """
        if self.state == ElevatorState.CLOSING:
            self.state = ElevatorState.OPENING
            self._action_timer = 0
            return True
        return False

    def extend_hold(self) -> bool:
        """
        开门状态下延长开门时间（有新乘客来时调用）。
        重置开门保持计时器，但受最长开门时间限制。
        返回是否成功延长（仅在 OPEN 状态下有效）。
        """
        if self.state == ElevatorState.OPEN and not self.overload:
            self._hold_timer = 0
            return True
        return False

    def _close_door(self) -> None:
        """内部方法：从 OPEN 状态转入 CLOSING。"""
        self.state = ElevatorState.CLOSING
        self._action_timer = 0
        self._total_open_time = 0
        # 记录关门开始时本层仍亮着的呼梯方向
        self._hall_up_at_closing = self.current_floor in self.hall_up
        self._hall_down_at_closing = self.current_floor in self.hall_down

    # ==================== 可视化插值属性（供动画界面使用） ====================
    @property
    def visual_position(self) -> float:
        """
        轿厢的连续楼层位置（浮点）：
        例如 5.5 表示轿厢位于 5 层与 6 层之间一半处，用于平滑动画。
        """
        if self.state == ElevatorState.MOVING_UP:
            # 从 current_floor 移动到 current_floor + 1
            return self.current_floor + min(1.0, self._action_timer / self.travel_time)
        if self.state == ElevatorState.MOVING_DOWN:
            # 从 current_floor 移动到 current_floor - 1
            return self.current_floor - min(1.0, self._action_timer / self.travel_time)
        return float(self.current_floor)

    @property
    def door_open_fraction(self) -> float:
        """门的打开程度：0=完全关闭，1=完全打开。"""
        if self.state == ElevatorState.OPENING:
            return min(1.0, self._action_timer / self.door_open_time)
        if self.state == ElevatorState.OPEN:
            return 1.0
        if self.state == ElevatorState.CLOSING:
            return max(0.0, 1.0 - self._action_timer / self.door_close_time)
        return 0.0

    # ==================== 状态描述（日志用） ====================
    def state_text(self) -> str:
        mapping = {
            ElevatorState.IDLE: "待机",
            ElevatorState.MOVING_UP: "上行",
            ElevatorState.MOVING_DOWN: "下行",
            ElevatorState.OPENING: "开门中",
            ElevatorState.OPEN: "开门保持",
            ElevatorState.CLOSING: "关门中",
            ElevatorState.FAULT: "故障",
        }
        return mapping[self.state]
