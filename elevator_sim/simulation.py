# -*- coding: utf-8 -*-
"""
仿真主循环与指标统计（阶段1）。

时间模型：离散时间步，每个 tick = 1 仿真秒。
每个 tick 的处理顺序：
    1. 客流生成（仅在客流时段内）
    2. 等待乘客放弃判定
    3. 电梯状态机推进
    4. 处理电梯事件（到站开门 -> 乘客进出 -> 消号；关门 -> 恢复运行）
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Iterable, Optional

import config
from .door_safety import DoorSafetySystem
from .elevator import Elevator, ElevatorState
from .load_cell import LoadCell
from .passenger import Passenger, PassengerStatus, PassengerIdAllocator
from .scenario import PassengerRequest
from .radar import RadarSystem
from .traffic import TrafficGenerator


@dataclass
class SimulationReport:
    """仿真结果统计报告。"""
    total_ticks: int = 0                    # 仿真总时长（秒）
    total_passengers: int = 0               # 总乘客数（含放弃）
    completed_passengers: int = 0           # 完成行程的乘客数
    abandoned_passengers: int = 0           # 放弃乘梯的乘客数
    total_stops: int = 0                    # 总停站次数
    empty_stops: int = 0                    # 空停次数（到站开门但无人进出）
    radar_cancellations: int = 0            # 雷达自动取消呼梯次数
    overload_count: int = 0                 # 超载发生次数
    overload_duration: int = 0              # 累计超载持续时间（秒）
    anti_pinch_reopens: int = 0             # 防夹重开次数
    avg_wait_time: float = 0.0             # 平均等待时间（秒）
    avg_travel_time: float = 0.0           # 平均全程时间（秒）
    wait_times: List[int] = field(default_factory=list)

    @property
    def empty_stop_rate(self) -> float:
        """空停率（空停次数 / 总停站次数）。"""
        return self.empty_stops / self.total_stops if self.total_stops else 0.0

    def print_report(self) -> None:
        print("=" * 56)
        print("           阶段1 基础电梯仿真 — 统计报告")
        print("=" * 56)
        print(f"仿真总时长（秒）        : {self.total_ticks}")
        print(f"总乘客数（含放弃）      : {self.total_passengers}")
        print(f"完成行程乘客数          : {self.completed_passengers}")
        print(f"放弃乘梯乘客数          : {self.abandoned_passengers}")
        print(f"总停站次数              : {self.total_stops}")
        print(f"空停次数                : {self.empty_stops}")
        print(f"雷达自动取消呼梯        : {self.radar_cancellations}")
        print(f"超载发生次数            : {self.overload_count}")
        print(f"累计超载时长（秒）      : {self.overload_duration}")
        print(f"防夹重开次数            : {self.anti_pinch_reopens}")
        print(f"空停率                  : {self.empty_stop_rate:.1%}")
        print(f"平均等待时间（秒）      : {self.avg_wait_time:.2f}")
        print(f"平均全程时间（秒）      : {self.avg_travel_time:.2f}")
        print("=" * 56)


class Simulation:
    """电梯仿真器。"""

    def __init__(self,
                 total_floors: int = config.TOTAL_FLOORS,
                 duration: int = config.SIMULATION_DURATION,
                 seed: int = config.RANDOM_SEED,
                 arrival_rate: float = config.CALL_ARRIVAL_RATE,
                 abandon_probability: float = config.ABANDON_PROBABILITY,
                 print_event: bool = config.PRINT_EVENT_LOG,
                 print_tick: bool = config.PRINT_TICK_LOG,
                 radar_enabled: bool = True,
                 load_cell_enabled: bool = True,
                 anti_pinch_enabled: bool = True,
                 hold_extension_enabled: bool = True,
                 requests: Optional[Iterable[PassengerRequest]] = None):
        self.now = 0
        self.duration = duration
        self.print_event = print_event
        self.print_tick = print_tick
        # 阶段5：功能开关（用于对照实验）
        self.radar_enabled = radar_enabled
        self.load_cell_enabled = load_cell_enabled
        self.anti_pinch_enabled = anti_pinch_enabled
        self.hold_extension_enabled = hold_extension_enabled

        rng = random.Random(seed)
        self.rng = rng
        # Incidental pedestrians must never consume the ordinary traffic RNG.
        self.pedestrian_rng = random.Random(f"pedestrians:{seed}")
        self.id_allocator = PassengerIdAllocator()
        self._request_schedule = None
        if requests is not None:
            self._request_schedule = {}
            for request in requests:
                request.validate(total_floors, duration)
                self._request_schedule.setdefault(request.call_time, []).append(request)

        self.elevator = Elevator(
            total_floors=total_floors,
            travel_time_per_floor=config.TRAVEL_TIME_PER_FLOOR,
            door_open_time=config.DOOR_OPEN_TIME,
            door_hold_time=config.DOOR_HOLD_TIME,
            door_close_time=config.DOOR_CLOSE_TIME,
        )
        self.traffic = TrafficGenerator(
            total_floors=total_floors,
            arrival_rate=arrival_rate,
            abandon_probability=abandon_probability,
            abandon_min_wait=config.ABANDON_MIN_WAIT,
            abandon_max_wait=config.ABANDON_MAX_WAIT,
            rng=rng,
            id_allocator=self.id_allocator,
        )
        # 阶段2：毫米波雷达系统
        self.radar = RadarSystem(total_floors=total_floors, enabled=radar_enabled)
        # 阶段3：轿厢负重传感器
        self.load_cell = LoadCell(enabled=load_cell_enabled)
        # 阶段4：关门防夹系统
        self.door_safety = DoorSafetySystem(enabled=anti_pinch_enabled)
        self.passengers: List[Passenger] = []
        # 防止仿真异常死循环的硬性上限（客流时长 + 充足的服务时间）
        self.max_ticks = duration + 10000

    # ---------------- 日志 ----------------
    def _log(self, text: str) -> None:
        if self.print_event:
            print(f"[{self.now:>5}s] {text}")

    # ---------------- 主循环 ----------------
    def run(self) -> SimulationReport:
        """命令行模式：按 tick 持续推进直到仿真结束。"""
        while self.now < self.max_ticks:
            self.step()
            if self.is_finished():
                break
        return self._build_report()

    def is_finished(self) -> bool:
        """结束判定：客流时段结束，且无等待/在梯乘客，电梯回到待机。"""
        waiting = [p for p in self.passengers
                   if p.status in (PassengerStatus.WAITING, PassengerStatus.IN_CAR)]
        return self.now >= self.duration and not waiting \
            and self.elevator.state == ElevatorState.IDLE

    def step(self) -> Dict[str, list]:
        """
        推进一个 tick（1 仿真秒），返回本 tick 的事件摘要，供可视化界面使用：
            new_call    : 新产生的呼梯乘客
            abandoned   : 新放弃乘梯的乘客
            open_at     : 本 tick 开门的楼层（None 表示未开门）
            leavers     : 到达出厢的乘客
            boarders    : 进入轿厢的乘客
            empty_stop  : 本次停靠是否为空停
            doors_closed: 本 tick 是否完成关门
        """
        result: Dict[str, list] = {
            "new_call": [], "abandoned": [], "open_at": None,
            "leavers": [], "boarders": [], "empty_stop": False,
            "doors_closed": False, "radar_cancelled": [],
            "anti_pinch_reopen": False,
        }

        # 1. 客流生成（仅在客流时段内）
        if self.now < self.duration:
            if self._request_schedule is None:
                arrivals = self.traffic.maybe_generate(self.now)
            else:
                arrivals = [Passenger(
                    pid=self.id_allocator.allocate(), origin=r.origin, target=r.target,
                    call_time=r.call_time, direction=1 if r.target > r.origin else -1,
                    abandon_time=r.abandon_time)
                    for r in self._request_schedule.get(self.now, ())]
            for p in arrivals:
                self.passengers.append(p)
                self.elevator.add_hall_call(p.origin, p.direction)
                result["new_call"].append(p)
                d_text = "上行" if p.direction == 1 else "下行"
                self._log(f"呼梯  {p.origin}层({d_text}) -> {p.target}层 "
                          f"[乘客#{p.pid}]"
                          f"{'，该乘客可能放弃' if p.abandon_time else ''}")

        # 2. 放弃判定
        for p in self.traffic.update_abandonment(self.passengers, self.now):
            result["abandoned"].append(p)
            self._log(f"放弃  {p.origin}层乘客#{p.pid}离开（呼梯按钮仍亮，"
                      f"可能造成空停）")

        # 2.5 阶段2：毫米波雷达检测 + 无人呼梯自动取消
        waiting_by_floor: Dict[int, int] = {}
        for p in self.passengers:
            if p.status == PassengerStatus.WAITING:
                waiting_by_floor[p.origin] = waiting_by_floor.get(p.origin, 0) + 1
        self.radar.set_presence_from_passengers(waiting_by_floor)
        cancelled = self.radar.check_auto_cancel(
            self.elevator.hall_up, self.elevator.hall_down,
            self.elevator.current_floor, self.elevator.direction,
        )
        for item in cancelled:
            f, d = item["floor"], item["direction"]
            if d == 1:
                self.elevator.hall_up.discard(f)
            else:
                self.elevator.hall_down.discard(f)
            result["radar_cancelled"].append(item)
            d_text = "上行" if d == 1 else "下行"
            self._log(f"雷达  {f}层{d_text}呼梯门前持续无人，自动取消")

        # 3. 电梯状态机推进
        prev_state = self.elevator.state
        event = self.elevator.tick()

        # 3.4 阶段4：关门防夹检测
        # 检测 OPEN -> CLOSING 转换，记录门前等待人数基线
        if (prev_state == ElevatorState.OPEN
                and self.elevator.state == ElevatorState.CLOSING):
            floor = self.elevator.current_floor
            waiting = self.door_safety.get_waiting_count(self.passengers, floor)
            self.door_safety.on_door_closing(floor, waiting)
        # CLOSING 过程中每tick检查是否有人闯入
        if self.elevator.state == ElevatorState.CLOSING:
            floor = self.elevator.current_floor
            # 模拟门前行人（有人走向电梯但未按按钮）
            self.door_safety.update_pedestrians(floor)
            current_waiting = self.door_safety.get_waiting_count(
                self.passengers, floor)
            if self.door_safety.check_intrusion(floor, current_waiting):
                if self.elevator.request_reopen():
                    self.door_safety.trigger_reopen(floor)
                    result["anti_pinch_reopen"] = True
                    # 将门前的行人转化为等待乘客（自动按同方向呼梯）
                    new_peds = self.door_safety.consume_pedestrians(floor)
                    for i in range(new_peds):
                        self._spawn_pedestrian_passenger(floor)
                    self._log(f"防夹  {floor}层检测到有人闯入，立即重新开门"
                              f"（{new_peds}人未按按钮直接进入）")

        # 3.5 阶段3：每tick更新载重传感器（运行中也实时监测）
        self.load_cell.update_from_passengers(self.passengers)
        self.elevator.overload = self.load_cell.overload

        # 3.6 阶段3：超载持续时，最后进入的乘客主动退出（真实电梯行为：
        # 超载报警后，最后进来的乘客通常会主动退出，直到载重降至额定以下）
        if (self.elevator.state == ElevatorState.OPEN
                and self.elevator.overload):
            self._handle_overload_exit()

        # 4. 事件处理
        if event == "arrived_open":
            info = self._handle_door_open()
            result.update(info)
        elif event == "doors_closed":
            result["doors_closed"] = True
            self._log("关门完成，电梯恢复运行")

        # 4.5 阶段4修复：开门期间有同方向新乘客等待时，让乘客进厢并延长开门
        # （放在事件处理之后，确保_handle_door_open先完成首次进厢和空停判定）
        # 每次开门最多延长一次（真实电梯行为：有人按按钮后门再保持一会儿，不是无限延长）
        if (self.hold_extension_enabled
                and self.elevator.state == ElevatorState.OPEN
                and not self.elevator.overload
                and not getattr(self, "_hold_extended_this_open", False)):
            floor = self.elevator.current_floor
            has_same_dir_waiting = any(
                p.status == PassengerStatus.WAITING
                and p.origin == floor
                and p.direction == self.elevator.direction
                for p in self.passengers
            )
            if has_same_dir_waiting:
                # 让新到达的乘客进厢
                boarders, _ = self._board_waiting_passengers()
                result["boarders"].extend(boarders)
                # 如果本次开门之前被判定为空停，但现在有乘客进来了，回滚空停计数
                if (boarders and getattr(self, "_last_open_was_empty", False)
                        and getattr(self, "_last_open_floor", None) == floor):
                    self._empty_stop_hits = max(0, self._empty_stop_hits - 1)
                    self._last_open_was_empty = False
                    self._log(f"修正  {floor}层开门期间有乘客到达，撤销空停计数")
                # 延长开门时间（本次开门只延长一次）
                self.elevator.extend_hold()
                self._hold_extended_this_open = True

        if self.print_tick:
            print(f"tick={self.now} 楼层={self.elevator.current_floor} "
                  f"状态={self.elevator.state_text()}")

        self.now += 1
        return result

    # ---------------- 到站开门：乘客进出 ----------------
    def _handle_door_open(self) -> Dict[str, list]:
        floor = self.elevator.current_floor
        served_dirs = self.elevator.served_directions_at_stop()
        # 重置开门延长标志（每次开门最多延长一次）
        self._hold_extended_this_open = False

        # 4.1 轿厢内乘客先离开（到达目标层）
        leavers = [p for p in self.passengers
                   if p.status == PassengerStatus.IN_CAR and p.target == floor]
        for p in leavers:
            p.status = PassengerStatus.DONE
            p.arrive_time = self.now
            self._log(f"到达  乘客#{p.pid}在{floor}层离开轿厢")
        self.elevator.car_calls.discard(floor)

        # 出厢后更新载重（可能解除超载）
        self.load_cell.update_from_passengers(self.passengers)
        self.elevator.overload = self.load_cell.overload

        # 4.2 厅外乘客进入（方向与本次服务方向一致）
        # 阶段3：逐个检查载重，超载时拒绝进入并保持开门报警
        boarders = []
        refused = []
        candidates = [p for p in self.passengers
                      if p.status == PassengerStatus.WAITING
                      and p.origin == floor
                      and p.direction in served_dirs]
        for p in candidates:
            if self.load_cell.can_accept():
                p.status = PassengerStatus.IN_CAR
                p.board_time = self.now
                self.elevator.add_car_call(p.target)
                boarders.append(p)
                self.load_cell.update_from_passengers(self.passengers)
                self._log(f"进厢  {floor}层乘客#{p.pid}进入轿厢，目标{p.target}层")
            else:
                # 载重不足，拒绝进入，乘客继续等待
                refused.append(p)
                self._log(f"超载  {floor}层乘客#{p.pid}被拒绝进入（轿厢已满）")
        # 更新电梯超载标志
        self.elevator.overload = self.load_cell.overload
        if self.load_cell.overload:
            self._log(f"报警  轿厢超载！当前{self.load_cell.current_load_kg:.0f}kg / "
                      f"额定{self.load_cell.rated_load_kg:.0f}kg，保持开门")

        # 4.3 清除本次服务方向的厅外呼梯（按钮消号）
        # 注意：如果有乘客被拒绝进入（超载），该方向呼梯保留，等下一趟
        if not refused:
            for d in served_dirs:
                if d == 1:
                    self.elevator.hall_up.discard(floor)
                else:
                    self.elevator.hall_down.discard(floor)

        # 4.4 空停判定：本次开门无人进出
        empty_stop = not leavers and not boarders
        if empty_stop:
            self._empty_stop_hits = getattr(self, "_empty_stop_hits", 0) + 1
            self._log(f"空停  电梯在{floor}层开门，但无人进出")
        # 记录本次开门状态（供开门延长期间修正空停计数）
        self._last_open_floor = floor
        self._last_open_was_empty = empty_stop

        return {"open_at": floor, "leavers": leavers,
                "boarders": boarders, "empty_stop": empty_stop,
                "refused": refused, "overload": self.load_cell.overload}

    # ---------------- 阶段4修复：OPEN状态下持续检查乘客进厢 ----------------
    def _board_waiting_passengers(self) -> tuple:
        """
        让当前层等待的、方向与服务方向一致的乘客进入轿厢。
        可在开门期间的每个tick调用，使晚到的乘客也能及时进入。
        返回 (boarders, refused)。
        """
        floor = self.elevator.current_floor
        served_dirs = self.elevator.served_directions_at_stop()
        boarders = []
        refused = []
        candidates = [p for p in self.passengers
                      if p.status == PassengerStatus.WAITING
                      and p.origin == floor
                      and p.direction in served_dirs]
        for p in candidates:
            if self.load_cell.can_accept():
                p.status = PassengerStatus.IN_CAR
                p.board_time = self.now
                self.elevator.add_car_call(p.target)
                boarders.append(p)
                self.load_cell.update_from_passengers(self.passengers)
                self._log(f"进厢  {floor}层乘客#{p.pid}进入轿厢，目标{p.target}层")
            else:
                refused.append(p)
                self._log(f"超载  {floor}层乘客#{p.pid}被拒绝进入（轿厢已满）")
        # 更新超载标志
        self.elevator.overload = self.load_cell.overload
        if self.load_cell.overload and boarders:
            self._log(f"报警  轿厢超载！当前{self.load_cell.current_load_kg:.0f}kg / "
                      f"额定{self.load_cell.rated_load_kg:.0f}kg，保持开门")
        # 清除本次服务方向的厅外呼梯（按钮消号）
        # 注意：如果有乘客被拒绝进入（超载），该方向呼梯保留，等下一趟
        if not refused:
            for d in served_dirs:
                if d == 1:
                    self.elevator.hall_up.discard(floor)
                else:
                    self.elevator.hall_down.discard(floor)
        return boarders, refused

    # ---------------- 超载处理：最后进入的乘客主动退出 ----------------
    def _handle_overload_exit(self) -> None:
        """
        超载报警持续时，最后进入轿厢的乘客主动退出（真实电梯行为）。
        每tick退出一人，直到载重降至额定以下。
        退出的乘客回到当前层等待状态，其呼梯按钮重新点亮。
        """
        in_car = [p for p in self.passengers
                  if p.status == PassengerStatus.IN_CAR]
        if not in_car:
            return
        # 按进入时间排序，最后进入的先退出
        in_car.sort(key=lambda p: p.board_time if p.board_time is not None else 0,
                    reverse=True)
        last = in_car[0]
        # 退出轿厢
        last.status = PassengerStatus.WAITING
        last.origin = self.elevator.current_floor
        last.board_time = None
        # 重新点亮该层呼梯（方向与原方向一致）
        self.elevator.add_hall_call(last.origin, last.direction)
        # 如果没有其他乘客去该乘客的目标层，移除内呼
        others_to_target = [p for p in self.passengers
                            if p.status == PassengerStatus.IN_CAR
                            and p.target == last.target]
        if not others_to_target:
            self.elevator.car_calls.discard(last.target)
        self._log(f"超载  乘客#{last.pid}主动退出轿厢，回到{last.origin}层等待")
        # 更新载重和超载标志
        self.load_cell.update_from_passengers(self.passengers)
        self.elevator.overload = self.load_cell.overload

    # ---------------- 阶段4修复：门前行人转化为等待乘客 ----------------
    def _spawn_pedestrian_passenger(self, floor: int) -> None:
        """
        防夹重开后，将门前的"未按按钮行人"转化为等待乘客。
        行人自动按同方向呼梯，目标楼层随机（与方向一致）。
        顶层自动改下行，底层自动改上行（避免目标=当前层的无效行程）。
        """
        direction = self.elevator.direction
        total = self.elevator.total_floors
        # 边界处理：顶层只能下行，底层只能上行
        if floor >= total:
            direction = -1
        elif floor <= 1:
            direction = 1
        # 根据方向选择目标楼层
        if direction == 1:
            target = self.pedestrian_rng.randint(floor + 1, total)
        else:
            target = self.pedestrian_rng.randint(1, floor - 1)

        # Also reserve IDs of manually injected passengers used by older clients.
        self.id_allocator.reserve(max((p.pid for p in self.passengers), default=0))
        pid = self.id_allocator.allocate()
        p = Passenger(
            pid=pid,
            origin=floor,
            target=target,
            call_time=self.now,
            direction=direction,
            abandon_time=None,  # 行人不放弃
        )
        self.passengers.append(p)
        self.elevator.add_hall_call(floor, direction)
        self._log(f"行人  {floor}层行人（未按按钮）被防夹系统开门，"
                  f"自动按{('上行' if direction == 1 else '下行')}，目标{target}层")

    # ---------------- 报告生成 ----------------
    def _build_report(self) -> SimulationReport:
        done = [p for p in self.passengers if p.status == PassengerStatus.DONE]
        abandoned = [p for p in self.passengers if p.status == PassengerStatus.ABANDONED]
        wait_times = [p.wait_time for p in done if p.wait_time is not None]
        travel_times = [p.travel_time for p in done if p.travel_time is not None]

        report = SimulationReport(
            total_ticks=self.now,
            total_passengers=len(self.passengers),
            completed_passengers=len(done),
            abandoned_passengers=len(abandoned),
            total_stops=self.elevator.stop_count,
            empty_stops=getattr(self, "_empty_stop_hits", 0),
            radar_cancellations=self.radar.auto_cancel_count,
            overload_count=self.load_cell.overload_count,
            overload_duration=self.load_cell.overload_duration,
            anti_pinch_reopens=self.door_safety.reopen_count,
            avg_wait_time=sum(wait_times) / len(wait_times) if wait_times else 0.0,
            avg_travel_time=sum(travel_times) / len(travel_times) if travel_times else 0.0,
            wait_times=wait_times,
        )
        return report
