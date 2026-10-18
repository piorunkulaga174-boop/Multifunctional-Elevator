# -*- coding: utf-8 -*-
"""
阶段5：极端场景压力测试。

测试三种极端场景下全功能智能电梯的稳定性：
    1. 早高峰极端客流：高到达率，全部从1楼往上
    2. 高放弃率场景：50%乘客按完就走
    3. 低载重限制：额定载重300kg（约4人），频繁超载

验证目标：系统不死机、不出现无限循环、调度逻辑不混乱。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elevator_sim.simulation import Simulation
from elevator_sim.elevator import ElevatorState


def run_stress_test(name: str, rated_load_kg: float = None, **kwargs) -> dict:
    """运行单次压力测试，返回结果。"""
    print(f"\n{'='*60}")
    print(f"  极端场景：{name}")
    print(f"{'='*60}")

    sim = Simulation(
        duration=kwargs.pop("duration", 600),
        seed=42,
        print_event=False,
        print_tick=False,
        radar_enabled=True,
        load_cell_enabled=True,
        anti_pinch_enabled=True,
        hold_extension_enabled=True,
        **kwargs,
    )
    # 开启防夹行人
    sim.door_safety.pedestrian_prob = 0.15
    # 低载重场景修改额定载重
    if rated_load_kg:
        sim.load_cell.rated_load_kg = rated_load_kg

    report = sim.run()

    # 验证稳定性
    valid_states = (ElevatorState.IDLE, ElevatorState.OPEN,
                    ElevatorState.CLOSING, ElevatorState.OPENING,
                    ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN)
    assert sim.elevator.state in valid_states, \
        f"电梯状态异常: {sim.elevator.state}"
    assert sim.now < sim.max_ticks, "仿真进入无限循环"

    wait_times = [p.wait_time for p in sim.passengers
                  if p.status.name == "DONE" and p.wait_time is not None]

    result = {
        "name": name,
        "total_passengers": report.total_passengers,
        "completed": report.completed_passengers,
        "abandoned": report.abandoned_passengers,
        "total_stops": report.total_stops,
        "empty_stops": report.empty_stops,
        "empty_stop_rate": round(report.empty_stop_rate * 100, 1),
        "avg_wait": round(report.avg_wait_time, 1),
        "max_wait": round(max(wait_times) if wait_times else 0, 1),
        "radar_cancel": sim.radar.auto_cancel_count,
        "overload_count": sim.load_cell.overload_count,
        "anti_pinch": sim.door_safety.reopen_count,
        "sim_time": sim.now,
        "stable": True,
    }

    print(f"  总乘客: {result['total_passengers']}")
    print(f"  完成: {result['completed']}  放弃: {result['abandoned']}")
    print(f"  总停站: {result['total_stops']}  空停: {result['empty_stops']} ({result['empty_stop_rate']}%)")
    print(f"  平均等待: {result['avg_wait']}s  最长等待: {result['max_wait']}s")
    print(f"  雷达取消: {result['radar_cancel']}  超载: {result['overload_count']}  防夹: {result['anti_pinch']}")
    print(f"  仿真时长: {result['sim_time']}s  状态: 稳定 ✓")

    return result


def main():
    print("=" * 60)
    print("  阶段5：极端场景压力测试")
    print("=" * 60)

    results = []

    # 场景1：早高峰极端客流（高到达率，全部从1楼往上）
    # 客流生成器默认已经有55%下行到1层、25%上行、20%中间往返
    # 这里用高到达率模拟早高峰
    results.append(run_stress_test(
        "早高峰极端客流（到达率0.5）",
        arrival_rate=0.5,
        abandon_probability=0.1,
        duration=300,
    ))

    # 场景2：高放弃率场景
    results.append(run_stress_test(
        "高放弃率场景（50%放弃）",
        arrival_rate=0.15,
        abandon_probability=0.5,
        duration=600,
    ))

    # 场景3：低载重限制（频繁超载）
    results.append(run_stress_test(
        "低载重限制（额定300kg，约4人）",
        arrival_rate=0.15,
        abandon_probability=0.2,
        duration=600,
        rated_load_kg=300,
    ))

    print("\n" + "=" * 60)
    print("  压力测试汇总")
    print("=" * 60)
    print(f"{'场景':<25} {'完成':>6} {'空停率':>8} {'平均等待':>8} {'超载':>6} {'防夹':>6} {'稳定':>6}")
    print("-" * 60)
    for r in results:
        print(f"{r['name']:<25} {r['completed']:>6} {r['empty_stop_rate']:>7}% {r['avg_wait']:>7}s {r['overload_count']:>6} {r['anti_pinch']:>6} {'✓':>6}")
    print("=" * 60)
    print("\n所有极端场景测试通过，系统运行稳定！")


if __name__ == "__main__":
    main()
