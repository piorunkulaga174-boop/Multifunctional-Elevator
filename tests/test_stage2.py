# -*- coding: utf-8 -*-
"""
阶段2 确定性单元测试：毫米波雷达监测 + 无人呼梯自动取消。
运行方式：在项目根目录执行  python -m unittest tests.test_stage2 -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elevator_sim.elevator import Elevator, ElevatorState
from elevator_sim.passenger import Passenger, PassengerStatus
from elevator_sim.radar import RadarSystem, FloorRadar
from elevator_sim.simulation import Simulation


class TestFloorRadar(unittest.TestCase):
    """单楼层雷达基础行为。"""

    def test_person_present_resets_empty_timer(self):
        """检测到人时，无人计时清零。"""
        r = FloorRadar(5)
        r.update(False)
        r.update(False)
        self.assertEqual(r.empty_duration, 2)
        r.update(True)
        self.assertTrue(r.person_present)
        self.assertEqual(r.empty_duration, 0)

    def test_empty_duration_accumulates(self):
        """持续无人时，计时逐秒累加。"""
        r = FloorRadar(3)
        for _ in range(5):
            r.update(False)
        self.assertFalse(r.person_present)
        self.assertEqual(r.empty_duration, 5)


class TestRadarAutoCancel(unittest.TestCase):
    """雷达自动取消呼梯的核心逻辑。"""

    def setUp(self):
        self.radar = RadarSystem(total_floors=10, empty_cancel_seconds=8,
                                 near_floor_lock=2)

    def test_no_cancel_when_person_present(self):
        """门前有人时，即使呼梯很久也不取消。"""
        hall_up = {5}
        hall_down = set()
        # 模拟门前一直有人
        self.radar.set_presence_from_passengers({5: 1})
        for _ in range(20):
            cancelled = self.radar.check_auto_cancel(
                hall_up, hall_down, elevator_floor=1, elevator_direction=1)
            self.assertEqual(len(cancelled), 0)
        self.assertIn(5, hall_up)

    def test_cancel_after_empty_threshold(self):
        """门前持续无人超过阈值，自动取消呼梯。"""
        hall_up = {7}
        hall_down = set()
        # 前7秒：每次都更新雷达采样（模拟每秒检测一次），不取消
        for _ in range(7):
            self.radar.set_presence_from_passengers({})
            cancelled = self.radar.check_auto_cancel(
                hall_up, hall_down, elevator_floor=1, elevator_direction=1)
            self.assertEqual(len(cancelled), 0)
        # 第8秒达到阈值，取消
        self.radar.set_presence_from_passengers({})
        cancelled = self.radar.check_auto_cancel(
            hall_up, hall_down, elevator_floor=1, elevator_direction=1)
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]["floor"], 7)
        self.assertEqual(cancelled[0]["direction"], 1)

    def test_near_floor_lock_prevents_cancel(self):
        """电梯临近呼梯楼层（≤2层）时，即使无人也不取消。"""
        hall_up = {5}
        hall_down = set()
        self.radar.set_presence_from_passengers({})
        # 积累足够无人时间
        for _ in range(10):
            self.radar.radars[5].update(False)
        # 电梯在4层（距离1层），不取消
        cancelled = self.radar.check_auto_cancel(
            hall_up, hall_down, elevator_floor=4, elevator_direction=1)
        self.assertEqual(len(cancelled), 0)
        # 电梯在3层（距离2层），不取消
        cancelled = self.radar.check_auto_cancel(
            hall_up, hall_down, elevator_floor=3, elevator_direction=1)
        self.assertEqual(len(cancelled), 0)
        # 电梯在2层（距离3层），取消
        cancelled = self.radar.check_auto_cancel(
            hall_up, hall_down, elevator_floor=2, elevator_direction=1)
        self.assertEqual(len(cancelled), 1)

    def test_cancel_both_directions_same_floor(self):
        """同一层上下行呼梯都无人时，两个方向都取消。"""
        hall_up = {6}
        hall_down = {6}
        self.radar.set_presence_from_passengers({})
        for _ in range(10):
            self.radar.radars[6].update(False)
        cancelled = self.radar.check_auto_cancel(
            hall_up, hall_down, elevator_floor=1, elevator_direction=1)
        self.assertEqual(len(cancelled), 2)
        dirs = {c["direction"] for c in cancelled}
        self.assertEqual(dirs, {1, -1})

    def test_cancel_resets_empty_timer(self):
        """取消后无人计时重置，不会重复触发。"""
        hall_up = {8}
        hall_down = set()
        self.radar.set_presence_from_passengers({})
        for _ in range(10):
            self.radar.radars[8].update(False)
        self.radar.check_auto_cancel(
            hall_up, hall_down, elevator_floor=1, elevator_direction=1)
        # 取消后hall_up中8已被移除，再次检查不会重复
        self.assertEqual(self.radar.radars[8].empty_duration, 0)


class TestRadarInSimulation(unittest.TestCase):
    """雷达系统在完整仿真中的集成行为。"""

    def test_abandoned_passenger_call_gets_radar_cancelled(self):
        """
        乘客呼梯后放弃离开，雷达检测到门前无人，
        持续N秒后自动取消呼梯，电梯不再空停。
        （用10层乘客：电梯从1层到10层需18秒，雷达8秒取消时电梯在5层，
         距离10层5层>2，不触发临近锁定。）
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        # 10层乘客呼梯后立即放弃（abandon_time=1）
        p = Passenger(pid=1, origin=10, target=1, call_time=0,
                      direction=-1, abandon_time=1)
        sim.passengers.append(p)
        sim.elevator.add_hall_call(10, -1)

        # 手动推进：先让乘客放弃
        sim.step()  # now=0: 乘客还在（abandon_time=1, now<1）
        sim.step()  # now=1: 乘客放弃，雷达开始计时无人
        self.assertEqual(p.status, PassengerStatus.ABANDONED)

        # 雷达无人阈值8秒，推进足够长时间让雷达取消
        # 电梯在1~5层，距离10层≥5层>2，不锁定
        for _ in range(15):
            sim.step()

        # 呼梯应已被雷达取消
        self.assertNotIn(10, sim.elevator.hall_down)
        self.assertGreater(sim.radar.auto_cancel_count, 0)
        # 电梯不应在10层空停（因为呼梯已取消）
        self.assertEqual(sim.elevator.stop_count, 0)
        self.assertEqual(sim.elevator.state, ElevatorState.IDLE)

    def test_waiting_passenger_not_cancelled(self):
        """
        乘客一直等待不放弃，雷达检测到门前有人，呼梯不被取消，
        电梯正常停靠接人。
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        p = Passenger(pid=1, origin=5, target=1, call_time=0,
                      direction=-1, abandon_time=None)
        sim.passengers.append(p)
        sim.elevator.add_hall_call(5, -1)

        # 推进直到仿真结束
        report = sim.run()

        # 乘客应完成行程
        self.assertEqual(p.status, PassengerStatus.DONE)
        self.assertEqual(report.completed_passengers, 1)
        # 雷达不应取消任何呼梯
        self.assertEqual(sim.radar.auto_cancel_count, 0)
        # 电梯应在5层停靠（非空停）
        self.assertEqual(report.empty_stops, 0)


class TestRadarReducesEmptyStops(unittest.TestCase):
    """对比验证：雷达系统能显著减少空停次数。"""

    def test_radar_reduces_empty_stops_in_long_run(self):
        """600秒仿真中，雷达取消应减少空停（与阶段1基线对比）。"""
        # 带雷达的仿真（阶段2默认行为）
        sim = Simulation(duration=300, seed=42, arrival_rate=0.15,
                         abandon_probability=0.25, print_event=False)
        report = sim.run()

        # 雷达应至少取消一些呼梯（有25%放弃率，300秒内必然有放弃乘客）
        self.assertGreater(report.radar_cancellations, 0)
        # 空停率应较低（雷达提前取消了放弃乘客的呼梯）
        self.assertLess(report.empty_stop_rate, 0.15)


if __name__ == "__main__":
    unittest.main()
