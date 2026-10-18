# -*- coding: utf-8 -*-
"""
阶段1 确定性单元测试（仅使用标准库 unittest）。
运行方式：在项目根目录执行  python -m unittest tests.test_stage1 -v
"""

import os
import sys
import unittest

# 让测试可以从项目根目录导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elevator_sim.elevator import Elevator, ElevatorState
from elevator_sim.passenger import Passenger, PassengerStatus
from elevator_sim.simulation import Simulation


def make_elevator():
    """10层、运行一层2秒、开门2秒、保持5秒、关门2秒。"""
    return Elevator(total_floors=10,
                    travel_time_per_floor=2,
                    door_open_time=2,
                    door_hold_time=5,
                    door_close_time=2)


def drive(e, ticks):
    """推进电梯指定 tick 数，收集事件。"""
    events = []
    for _ in range(ticks):
        evt = e.tick()
        if evt:
            events.append(evt)
    return events


class TestEmptyStop(unittest.TestCase):
    """场景：乘客呼梯后放弃，按钮仍亮，电梯到站应记一次空停。"""

    def test_abandoned_call_causes_empty_stop(self):
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        p = Passenger(pid=1, origin=5, target=1, call_time=0,
                      direction=-1, abandon_time=3)
        sim.passengers.append(p)
        sim.elevator.add_hall_call(5, -1)

        report = sim.run()

        self.assertEqual(report.abandoned_passengers, 1)
        self.assertEqual(report.completed_passengers, 0)
        self.assertEqual(report.total_stops, 1)
        self.assertEqual(report.empty_stops, 1)
        self.assertEqual(report.empty_stop_rate, 1.0)
        self.assertEqual(sim.elevator.state, ElevatorState.IDLE)


class TestNormalRide(unittest.TestCase):
    """场景：乘客正常等待并乘梯到达，不应出现空停。"""

    def test_normal_ride_no_empty_stop(self):
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        p = Passenger(pid=1, origin=5, target=1, call_time=0,
                      direction=-1, abandon_time=None)
        sim.passengers.append(p)
        sim.elevator.add_hall_call(5, -1)

        report = sim.run()

        self.assertEqual(report.completed_passengers, 1)
        self.assertEqual(report.abandoned_passengers, 0)
        self.assertEqual(report.empty_stops, 0)
        self.assertEqual(p.status, PassengerStatus.DONE)
        # 精确时序：上行8s + 开门2s + 保持5s + 关门2s + 下行8s + 开门2s = 27s
        self.assertEqual(p.board_time, 10)
        self.assertEqual(p.arrive_time, 27)


class TestReopenDuringClosing(unittest.TestCase):
    """场景：关门期间本层出现新呼梯，关门完成后应立即重新开门。"""

    def test_reopen_for_new_same_floor_call(self):
        e = make_elevator()
        e.current_floor = 5
        e.state = ElevatorState.OPENING
        e._action_timer = 0

        drive(e, 2)                       # 开门完成 -> OPEN
        self.assertEqual(e.state, ElevatorState.OPEN)
        drive(e, 5)                       # 保持结束 -> CLOSING
        self.assertEqual(e.state, ElevatorState.CLOSING)
        e.add_hall_call(5, -1)            # 关门期间本层新呼下行
        events = drive(e, 2)              # 关门完成

        self.assertIn("doors_closed", events)
        self.assertEqual(e.state, ElevatorState.OPENING)


class TestReverseCallDuringClosing(unittest.TestCase):
    """场景：电梯下行（轿厢内有下方目标），关门期间本层出现"上行"新呼梯，
    方向相反不顺路，不应重开，应正常下行，该呼梯留待后续服务。"""

    def test_no_reopen_for_opposite_direction_call(self):
        e = make_elevator()
        e.current_floor = 7
        e.direction = -1
        e.state = ElevatorState.OPENING
        e._action_timer = 0
        e.add_car_call(2)                  # 轿厢内有乘客去2层（下方）

        drive(e, 2)                        # 开门完成
        drive(e, 5)                        # 保持
        self.assertEqual(e.state, ElevatorState.CLOSING)
        e.add_hall_call(7, 1)             # 关门期间本层新呼上行（反向）
        drive(e, 2)                        # 关门完成
        self.assertEqual(e.state, ElevatorState.MOVING_DOWN)
        self.assertIn(7, e.hall_up)        # 上行呼梯仍登记，等待后续服务


class TestReverseCallNoReopenLoop(unittest.TestCase):
    """场景：上行停靠时本层只有反向呼梯且上方有请求，关门后应继续上行，
    不得因反向呼梯反复开门（死循环）。"""

    def test_continue_up_with_reverse_hall_call(self):
        e = make_elevator()
        e.current_floor = 5
        e.direction = 1
        e.state = ElevatorState.OPENING
        e._action_timer = 0
        e.add_hall_call(5, -1)            # 本层反向（下行）呼梯
        e.add_hall_call(8, 1)             # 上方仍有上行请求

        drive(e, 2)                       # 开门完成
        served = e.served_directions_at_stop()
        self.assertEqual(served, [])      # 上行时不服务反向呼梯
        drive(e, 5)                       # 保持
        drive(e, 2)                       # 关门完成
        self.assertEqual(e.state, ElevatorState.MOVING_UP)


class TestScanSchedulingRealWorld(unittest.TestCase):
    """按真实电梯行为验证集选（SCAN）调度：上行只开上行门、下行只开下行门、
    到顶/到底才换向，顺路呼梯优先。"""

    def _make_sim(self, passengers):
        sim = Simulation(total_floors=10, duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        sim.passengers = passengers
        for p in passengers:
            sim.elevator.add_hall_call(p.origin, p.direction)
        return sim

    def _collect_stops(self, sim):
        stops = []
        while not sim.is_finished() and sim.now < 500:
            ev = sim.step()
            if ev["open_at"] is not None:
                stops.append(ev["open_at"])
        return stops

    def test_up_skips_down_call_then_serves_after_reversal(self):
        """3层下行 + 4层上行：上行先接4层，换向下行再接3层。"""
        sim = self._make_sim([
            Passenger(pid=1, origin=3, target=1, call_time=0, direction=-1),
            Passenger(pid=2, origin=4, target=8, call_time=0, direction=1),
        ])
        stops = self._collect_stops(sim)
        # 4层(上行)必须在3层(下行)之前被服务
        self.assertLess(stops.index(4), stops.index(3))
        self.assertEqual(stops, [4, 8, 3, 1])

    def test_both_down_calls_serve_top_first(self):
        """3层下行 + 4层下行（都按下行）：上行经过3层不停，到4层换向，再下行接3层。"""
        sim = self._make_sim([
            Passenger(pid=1, origin=3, target=1, call_time=0, direction=-1),
            Passenger(pid=2, origin=4, target=1, call_time=0, direction=-1),
        ])
        stops = self._collect_stops(sim)
        # 4层必须在3层之前（先到高层换向）
        self.assertLess(stops.index(4), stops.index(3))
        self.assertEqual(stops, [4, 3, 1])

    def test_up_serves_all_up_calls_before_reversal(self):
        """1层上行 + 5层上行 + 8层上行：一次上行全部接完，再换向。"""
        sim = self._make_sim([
            Passenger(pid=1, origin=1, target=6, call_time=0, direction=1),
            Passenger(pid=2, origin=5, target=9, call_time=0, direction=1),
            Passenger(pid=3, origin=8, target=10, call_time=0, direction=1),
        ])
        stops = self._collect_stops(sim)
        # 上行阶段：1层接#1 -> 5层接#2 -> 6层#1出(内呼) -> 8层接#3
        # -> 9层#2出(内呼) -> 10层#3出(内呼)
        self.assertEqual(stops, [1, 5, 6, 8, 9, 10])
        # 所有乘客完成
        self.assertEqual(sim.passengers[0].status, PassengerStatus.DONE)
        self.assertEqual(sim.passengers[1].status, PassengerStatus.DONE)
        self.assertEqual(sim.passengers[2].status, PassengerStatus.DONE)


class TestTrafficDistribution(unittest.TestCase):
    """客流分布应符合真实楼宇：大部分人下行到1层。"""

    def test_most_passengers_go_to_1f(self):
        sim = Simulation(total_floors=10, duration=300, seed=42,
                         arrival_rate=0.15, abandon_probability=0.0,
                         print_event=False)
        down_to_1 = up_from_1 = mid = 0
        while sim.now < 300:
            ev = sim.step()
            for p in ev["new_call"]:
                if p.target == 1:
                    down_to_1 += 1
                elif p.origin == 1:
                    up_from_1 += 1
                else:
                    mid += 1
        total = down_to_1 + up_from_1 + mid
        self.assertGreater(total, 20)
        # 下行到1层应占比最高（约55%）
        self.assertGreater(down_to_1 / total, 0.4)
        # 三类都应有
        self.assertGreater(down_to_1, 0)
        self.assertGreater(up_from_1, 0)
        self.assertGreater(mid, 0)


class TestLongRunTerminates(unittest.TestCase):
    """长仿真必须在保护上限内正常结束（状态机无死循环）。"""

    def test_300s_run_terminates(self):
        sim = Simulation(duration=300, seed=7, print_event=False)
        report = sim.run()
        self.assertLess(report.total_ticks, sim.max_ticks)
        # 所有乘客要么完成要么放弃
        self.assertEqual(report.completed_passengers + report.abandoned_passengers,
                         report.total_passengers)
        self.assertEqual(sim.elevator.state, ElevatorState.IDLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
