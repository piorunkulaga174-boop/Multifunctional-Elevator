# -*- coding: utf-8 -*-
"""
阶段3 确定性单元测试：轿厢负重检测与超载控制。
运行方式：在项目根目录执行  python -m unittest tests.test_stage3 -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elevator_sim.elevator import Elevator, ElevatorState
from elevator_sim.load_cell import LoadCell
from elevator_sim.passenger import Passenger, PassengerStatus
from elevator_sim.simulation import Simulation


class TestLoadCell(unittest.TestCase):
    """负重传感器基础行为。"""

    def test_load_calculated_from_passengers(self):
        """载重 = 轿厢内乘客数 × 单人均重。"""
        lc = LoadCell(rated_load_kg=1000, person_weight_kg=75)
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        p2 = Passenger(pid=2, origin=2, target=6, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        lc.update_from_passengers([p1, p2])
        self.assertEqual(lc.current_load_kg, 150)
        self.assertFalse(lc.overload)

    def test_overload_triggered(self):
        """载重达到额定值时判定超载。"""
        lc = LoadCell(rated_load_kg=150, person_weight_kg=75)
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        p2 = Passenger(pid=2, origin=2, target=6, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        lc.update_from_passengers([p1, p2])
        self.assertTrue(lc.overload)  # 150 >= 150

    def test_can_accept_check(self):
        """can_accept 判断是否还能再进一人。"""
        lc = LoadCell(rated_load_kg=200, person_weight_kg=75)
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        p2 = Passenger(pid=2, origin=2, target=6, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        lc.update_from_passengers([p1, p2])  # 150kg
        # 150+75=225 > 200，不能再进人
        self.assertFalse(lc.can_accept())
        # 去掉一人后 75+75=150 <= 200，可以进
        lc.update_from_passengers([p1])
        self.assertTrue(lc.can_accept())

    def test_overload_count_rising_edge(self):
        """超载次数只在上升沿计数，持续超载不重复计数。"""
        lc = LoadCell(rated_load_kg=75, person_weight_kg=75)
        p = Passenger(pid=1, origin=1, target=5, call_time=0,
                      direction=1, status=PassengerStatus.IN_CAR)
        lc.update_from_passengers([p])  # 超载
        self.assertEqual(lc.overload_count, 1)
        lc.update_from_passengers([p])  # 仍超载
        self.assertEqual(lc.overload_count, 1)  # 不重复计数
        lc.update_from_passengers([])   # 解除
        lc.update_from_passengers([p])  # 再次超载
        self.assertEqual(lc.overload_count, 2)

    def test_overload_duration_accumulates(self):
        """超载持续时间逐秒累加。"""
        lc = LoadCell(rated_load_kg=75, person_weight_kg=75)
        p = Passenger(pid=1, origin=1, target=5, call_time=0,
                      direction=1, status=PassengerStatus.IN_CAR)
        for _ in range(5):
            lc.update_from_passengers([p])
        self.assertEqual(lc.overload_duration, 5)


class TestOverloadInSimulation(unittest.TestCase):
    """超载在完整仿真中的行为。"""

    def test_overload_prevents_boarding(self):
        """
        轿厢已满（超载）时，新乘客被拒绝进入，
        电梯保持开门，直到有人出厢。
        """
        # 额定载重=150kg（2人），单人75kg
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        sim.load_cell.rated_load_kg = 150
        sim.load_cell.person_weight_kg = 75

        # 预先放2人在轿厢内（已超载：150kg）
        p1 = Passenger(pid=1, origin=1, target=10, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        p2 = Passenger(pid=2, origin=1, target=9, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        sim.passengers.extend([p1, p2])
        sim.elevator.add_car_call(10)
        sim.elevator.add_car_call(9)
        sim.elevator.current_floor = 5
        sim.elevator.state = ElevatorState.OPEN
        sim.elevator.direction = 1
        sim.elevator._hold_timer = 0

        # 5层有1人等待上行
        p3 = Passenger(pid=3, origin=5, target=8, call_time=0,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p3)
        sim.elevator.add_hall_call(5, 1)

        # 手动触发开门处理（模拟到达5层开门）
        info = sim._handle_door_open()

        # p3应被拒绝进入（超载）
        self.assertEqual(p3.status, PassengerStatus.WAITING)
        self.assertIn(p3, info["refused"])
        self.assertTrue(info["overload"])
        # 电梯应保持开门状态（超载不计时）
        self.assertTrue(sim.elevator.overload)

    def test_overload_door_stays_open(self):
        """超载时电梯OPEN状态不计时、不关门。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.OPEN
        e.overload = True
        e._hold_timer = 0

        # 推进100 tick，超载时应一直保持OPEN
        for _ in range(100):
            e.tick()
        self.assertEqual(e.state, ElevatorState.OPEN)

        # 解除超载后，应在door_hold_time后关门
        e.overload = False
        for _ in range(5):
            e.tick()
        self.assertEqual(e.state, ElevatorState.CLOSING)

    def test_overload_cleared_after_passengers_leave(self):
        """
        乘客出厢后载重降低，超载解除，电梯恢复正常运行。
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        sim.load_cell.rated_load_kg = 150
        sim.load_cell.person_weight_kg = 75

        # 2人在轿厢内去1层（超载150kg）
        p1 = Passenger(pid=1, origin=5, target=1, call_time=0,
                       direction=-1, status=PassengerStatus.IN_CAR)
        p2 = Passenger(pid=2, origin=5, target=1, call_time=0,
                       direction=-1, status=PassengerStatus.IN_CAR)
        sim.passengers.extend([p1, p2])
        sim.elevator.add_car_call(1)
        sim.elevator.current_floor = 1
        sim.elevator.state = ElevatorState.OPEN
        sim.elevator.direction = -1
        sim.elevator._hold_timer = 0

        # 到达1层开门，2人出厢
        info = sim._handle_door_open()
        self.assertEqual(len(info["leavers"]), 2)
        self.assertFalse(sim.elevator.overload)
        self.assertEqual(sim.load_cell.current_load_kg, 0)

    def test_normal_load_no_overload(self):
        """载重未超额定值时，乘客正常进入，不触发超载。"""
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        sim.load_cell.rated_load_kg = 1000  # 大额定，不会超载

        p = Passenger(pid=1, origin=5, target=1, call_time=0,
                      direction=-1, status=PassengerStatus.WAITING)
        sim.passengers.append(p)
        sim.elevator.add_hall_call(5, -1)
        sim.elevator.current_floor = 5
        sim.elevator.state = ElevatorState.OPEN
        sim.elevator.direction = -1
        sim.elevator._hold_timer = 0

        info = sim._handle_door_open()
        self.assertEqual(p.status, PassengerStatus.IN_CAR)
        self.assertEqual(len(info["refused"]), 0)
        self.assertFalse(info["overload"])


class TestOverloadHallCallRetention(unittest.TestCase):
    """超载时被拒绝的乘客，其呼梯按钮应保留（等下一趟）。"""

    def test_refused_passenger_call_not_cleared(self):
        """超载拒绝乘客进入后，该层呼梯不消除，等下一趟电梯。"""
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        sim.load_cell.rated_load_kg = 150
        sim.load_cell.person_weight_kg = 75

        # 轿厢内2人（超载）
        p1 = Passenger(pid=1, origin=1, target=10, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        p2 = Passenger(pid=2, origin=1, target=9, call_time=0,
                       direction=1, status=PassengerStatus.IN_CAR)
        sim.passengers.extend([p1, p2])
        sim.elevator.add_car_call(10)
        sim.elevator.add_car_call(9)

        # 5层有人等待上行
        p3 = Passenger(pid=3, origin=5, target=8, call_time=0,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p3)
        sim.elevator.add_hall_call(5, 1)

        sim.elevator.current_floor = 5
        sim.elevator.state = ElevatorState.OPEN
        sim.elevator.direction = 1
        sim.elevator._hold_timer = 0

        sim._handle_door_open()

        # 5层上行呼梯应保留（因为p3被拒绝了）
        self.assertIn(5, sim.elevator.hall_up)
        self.assertEqual(p3.status, PassengerStatus.WAITING)


if __name__ == "__main__":
    unittest.main()
