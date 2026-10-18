# -*- coding: utf-8 -*-
"""
阶段4 确定性单元测试：关门防夹与行人闯入重开保护。
运行方式：在项目根目录执行  python -m unittest tests.test_stage4 -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elevator_sim.door_safety import DoorSafetySystem
from elevator_sim.elevator import Elevator, ElevatorState
from elevator_sim.passenger import Passenger, PassengerStatus
from elevator_sim.simulation import Simulation


class TestDoorSafetySystem(unittest.TestCase):
    """门控安全系统基础行为。"""

    def test_no_intrusion_when_waiting_unchanged(self):
        """关门过程中等待人数不变，不触发闯入。"""
        ds = DoorSafetySystem()
        ds.on_door_closing(5, waiting_count=2)
        self.assertFalse(ds.check_intrusion(5, current_waiting=2))

    def test_intrusion_when_waiting_increases(self):
        """关门过程中等待人数增加，触发闯入。"""
        ds = DoorSafetySystem()
        ds.on_door_closing(5, waiting_count=1)
        self.assertTrue(ds.check_intrusion(5, current_waiting=2))

    def test_no_intrusion_when_person_waits_but_no_increase(self):
        """
        关门开始时门前有人且一直没走（人数不增加），不触发重开。
        （可能是反向呼梯乘客在等下一趟，不应导致电梯永远关不上门）
        """
        ds = DoorSafetySystem()
        ds.on_door_closing(5, waiting_count=1)
        self.assertFalse(ds.check_intrusion(5, current_waiting=1))

    def test_no_intrusion_when_no_one_waiting(self):
        """门前无人，不触发。"""
        ds = DoorSafetySystem()
        ds.on_door_closing(5, waiting_count=0)
        self.assertFalse(ds.check_intrusion(5, current_waiting=0))

    def test_disabled_system_never_triggers(self):
        """系统禁用时永不触发。"""
        ds = DoorSafetySystem(enabled=False)
        ds.on_door_closing(5, waiting_count=0)
        self.assertFalse(ds.check_intrusion(5, current_waiting=5))

    def test_reopen_count_increments(self):
        """触发重开后计数增加。"""
        ds = DoorSafetySystem()
        ds.trigger_reopen(5)
        ds.trigger_reopen(3)
        self.assertEqual(ds.reopen_count, 2)
        self.assertEqual(ds.last_reopen_floor, 3)

    def test_get_waiting_count(self):
        """统计指定楼层等待人数。"""
        ds = DoorSafetySystem()
        p1 = Passenger(pid=1, origin=5, target=1, call_time=0,
                       direction=-1, status=PassengerStatus.WAITING)
        p2 = Passenger(pid=2, origin=5, target=2, call_time=0,
                       direction=-1, status=PassengerStatus.WAITING)
        p3 = Passenger(pid=3, origin=3, target=1, call_time=0,
                       direction=-1, status=PassengerStatus.WAITING)
        self.assertEqual(ds.get_waiting_count([p1, p2, p3], 5), 2)
        self.assertEqual(ds.get_waiting_count([p1, p2, p3], 3), 1)
        self.assertEqual(ds.get_waiting_count([p1, p2, p3], 7), 0)


class TestElevatorReopen(unittest.TestCase):
    """电梯防夹重开方法。"""

    def test_request_reopen_during_closing(self):
        """CLOSING状态下请求重开成功。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.CLOSING
        e._action_timer = 1
        self.assertTrue(e.request_reopen())
        self.assertEqual(e.state, ElevatorState.OPENING)
        self.assertEqual(e._action_timer, 0)

    def test_request_reopen_ignored_when_not_closing(self):
        """非CLOSING状态下请求重开无效。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.MOVING_UP
        self.assertFalse(e.request_reopen())
        self.assertEqual(e.state, ElevatorState.MOVING_UP)


class TestAntiPinchInSimulation(unittest.TestCase):
    """防夹在完整仿真中的行为。"""

    def test_new_passenger_arrives_during_closing_triggers_reopen(self):
        """
        关门过程中新乘客到达该层呼梯，触发防夹重开。
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        # 1层有1人等待上行去5层
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p1)
        sim.elevator.add_hall_call(1, 1)

        # 推进到开门、乘客进入、开始关门
        # 电梯IDLE->MOVING->到1层(已经在1层)->OPENING->OPEN
        for _ in range(5):
            sim.step()
        # 此时p1应该已进厢，门在OPEN或CLOSING
        # 手动确保门在CLOSING状态
        sim.elevator.state = ElevatorState.CLOSING
        sim.elevator._action_timer = 0
        sim.elevator.current_floor = 1
        sim.elevator.direction = 1
        # 记录关门开始时的等待人数（0人，因为p1已进厢）
        sim.door_safety.on_door_closing(1, 0)

        # 关门过程中，新乘客p2到达1层
        p2 = Passenger(pid=2, origin=1, target=8, call_time=sim.now,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p2)
        sim.elevator.add_hall_call(1, 1)

        # 推进一个tick，应触发防夹重开
        result = sim.step()
        self.assertTrue(result["anti_pinch_reopen"])
        self.assertEqual(sim.elevator.state, ElevatorState.OPENING)
        self.assertGreater(sim.door_safety.reopen_count, 0)

    def test_no_reopen_when_no_one_at_door(self):
        """
        关门过程中门前无人，正常关门，不触发防夹。
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        # 1层有1人去5层
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p1)
        sim.elevator.add_hall_call(1, 1)

        # 推进到乘客进厢后关门
        reopen_count_before = 0
        for _ in range(20):
            result = sim.step()
            if result.get("anti_pinch_reopen"):
                reopen_count_before += 1
            if sim.elevator.state in (ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN):
                break

        # 电梯应该已经关门运行（没有因为门前无人而重开）
        self.assertIn(sim.elevator.state,
                      (ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN, ElevatorState.IDLE))
        # p1应已进厢
        self.assertEqual(p1.status, PassengerStatus.IN_CAR)

    def test_reopen_allows_late_passenger_to_board(self):
        """
        防夹重开后，晚到的乘客能进入轿厢。
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p1)
        sim.elevator.add_hall_call(1, 1)

        # 推进到p1进厢后门开始关闭
        for _ in range(8):
            sim.step()

        # 确保门在CLOSING
        if sim.elevator.state == ElevatorState.OPEN:
            sim.elevator._hold_timer = 100  # 强制超时关门
            sim.step()

        # 此时p2到达
        p2 = Passenger(pid=2, origin=1, target=8, call_time=sim.now,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p2)
        sim.elevator.add_hall_call(1, 1)

        # 推进直到p2进厢或仿真结束
        for _ in range(30):
            sim.step()
            if p2.status == PassengerStatus.IN_CAR:
                break

        self.assertEqual(p2.status, PassengerStatus.IN_CAR)


class TestAntiPinchWithMultipleFloors(unittest.TestCase):
    """防夹系统在多楼层场景下的独立性。"""

    def test_intrusion_check_is_per_floor(self):
        """闯入检测按楼层独立，不互相干扰。"""
        ds = DoorSafetySystem()
        ds.on_door_closing(3, waiting_count=0)
        ds.on_door_closing(7, waiting_count=1)
        # 3层无人且不增加，不触发
        self.assertFalse(ds.check_intrusion(3, 0))
        # 7层等待人数从1增加到2（有人新走来），触发
        self.assertTrue(ds.check_intrusion(7, 2))
        # 3层仍然不触发（独立）
        self.assertFalse(ds.check_intrusion(3, 0))


class TestDoorHoldExtension(unittest.TestCase):
    """开门延长机制（阶段4修复）。"""

    def test_extend_hold_resets_timer(self):
        """OPEN状态下调用extend_hold重置开门计时器。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.OPEN
        e._hold_timer = 4  # 快关门了
        self.assertTrue(e.extend_hold())
        self.assertEqual(e._hold_timer, 0)

    def test_extend_hold_keeps_door_open(self):
        """持续延长开门，门不会在正常时间关闭。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.OPEN
        e._hold_timer = 0
        # 正常5秒后关门，但每tick都延长
        for _ in range(10):
            e.tick()
            e.extend_hold()
        self.assertEqual(e.state, ElevatorState.OPEN)

    def test_max_hold_time_forces_close(self):
        """超过最长开门时间（30秒）强制关门。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.OPEN
        e.max_hold_time = 10  # 缩短测试时间
        e._hold_timer = 0
        # 每tick延长，但超过最长时间后强制关门
        for _ in range(15):
            e.tick()
            e.extend_hold()
            if e.state == ElevatorState.CLOSING:
                break
        self.assertEqual(e.state, ElevatorState.CLOSING)

    def test_extend_hold_ignored_when_overload(self):
        """超载时extend_hold无效（超载本身就保持开门）。"""
        e = Elevator(total_floors=10, travel_time_per_floor=2,
                     door_open_time=2, door_hold_time=5, door_close_time=2)
        e.state = ElevatorState.OPEN
        e.overload = True
        e._hold_timer = 0
        self.assertFalse(e.extend_hold())


class TestPedestrianDetection(unittest.TestCase):
    """门前行人检测（未按按钮的人走向电梯）。"""

    def test_pedestrian_walks_and_triggers_at_door(self):
        """行人从远处走来，到达门口时触发防夹重开。"""
        ds = DoorSafetySystem(pedestrian_prob=1.0, pedestrian_start_distance=3)
        ds.on_door_closing(5, waiting_count=0)
        ds.update_pedestrians(5)  # 出现1个行人（distance=3）
        self.assertGreater(ds.get_pedestrian_count(5), 0)
        # 还没到门口，不触发
        self.assertFalse(ds.check_intrusion(5, current_waiting=0))
        # 走3步到达门口
        for _ in range(3):
            ds.update_pedestrians(5)
        # 到达门口，触发
        self.assertTrue(ds.check_intrusion(5, current_waiting=0))

    def test_pedestrian_consumed_after_reopen(self):
        """防夹重开后行人被消费（转化为等待乘客）。"""
        from elevator_sim.door_safety import Pedestrian
        ds = DoorSafetySystem()
        ds.on_door_closing(5, waiting_count=0)
        ds._pedestrians[5] = [Pedestrian(0), Pedestrian(0)]  # 手动设置2个已到门口的行人
        consumed = ds.consume_pedestrians(5)
        self.assertEqual(consumed, 2)
        self.assertEqual(ds.get_pedestrian_count(5), 0)

    def test_no_pedestrian_no_trigger(self):
        """门前没有行人且等待不增加，不触发。"""
        ds = DoorSafetySystem(pedestrian_prob=0.0)  # 0%出现行人
        ds.on_door_closing(5, waiting_count=0)
        ds.update_pedestrians(5)
        self.assertEqual(ds.get_pedestrian_count(5), 0)
        self.assertFalse(ds.check_intrusion(5, current_waiting=0))

    def test_pedestrian_progress(self):
        """行人接近进度从0增加到1。"""
        from elevator_sim.door_safety import Pedestrian
        p = Pedestrian(start_distance=4)
        self.assertAlmostEqual(p.progress, 0.0)
        p.step_closer()
        self.assertAlmostEqual(p.progress, 0.25)
        for _ in range(3):
            p.step_closer()
        self.assertAlmostEqual(p.progress, 1.0)
        self.assertTrue(p.at_door)


class TestOpenHoldExtensionInSimulation(unittest.TestCase):
    """开门延长在完整仿真中的行为。"""

    def test_new_passenger_during_open_extends_hold(self):
        """
        开门期间有同方向新乘客到达，开门时间延长，
        乘客能进入轿厢（不会被关在外面）。
        """
        sim = Simulation(duration=0, arrival_rate=0.0,
                         abandon_probability=0.0, print_event=False)
        # 1层有1人等待上行去5层
        p1 = Passenger(pid=1, origin=1, target=5, call_time=0,
                       direction=1, status=PassengerStatus.WAITING)
        sim.passengers.append(p1)
        sim.elevator.add_hall_call(1, 1)

        # 推进到开门状态
        for _ in range(5):
            sim.step()
        # p1应已进厢
        self.assertEqual(p1.status, PassengerStatus.IN_CAR)

        # 门还开着时，p2到达1层上行
        if sim.elevator.state == ElevatorState.OPEN:
            p2 = Passenger(pid=2, origin=1, target=8, call_time=sim.now,
                           direction=1, status=PassengerStatus.WAITING)
            sim.passengers.append(p2)
            sim.elevator.add_hall_call(1, 1)
            # 推进几个tick，开门延长机制应让p2进来
            for _ in range(8):
                sim.step()
                if p2.status == PassengerStatus.IN_CAR:
                    break
            self.assertEqual(p2.status, PassengerStatus.IN_CAR)


if __name__ == "__main__":
    unittest.main()
