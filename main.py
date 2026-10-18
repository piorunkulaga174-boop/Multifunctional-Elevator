# -*- coding: utf-8 -*-
"""
多功能电梯智能呼梯仿真系统 —— 运行入口（阶段1：基础电梯运行仿真）

运行方式：
    python main.py                  # 使用默认参数运行
    python main.py --duration 300   # 指定客流时长 300 秒
    python main.py --seed 1         # 指定随机种子
    python main.py --no-log         # 关闭事件日志，只看统计结果
"""

import argparse

import config
from elevator_sim.simulation import Simulation


def main():
    parser = argparse.ArgumentParser(description="多功能电梯智能呼梯仿真系统（阶段1）")
    parser.add_argument("--floors", type=int, default=config.TOTAL_FLOORS,
                        help="总楼层数（默认取 config.py）")
    parser.add_argument("--duration", type=int, default=config.SIMULATION_DURATION,
                        help="客流生成持续时长（秒）")
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED,
                        help="随机种子（相同种子结果可复现）")
    parser.add_argument("--rate", type=float, default=config.CALL_ARRIVAL_RATE,
                        help="每秒产生新乘客的概率")
    parser.add_argument("--abandon", type=float, default=config.ABANDON_PROBABILITY,
                        help="乘客呼梯后放弃乘梯的概率")
    parser.add_argument("--no-log", action="store_true",
                        help="关闭事件日志，仅输出最终统计")
    parser.add_argument("--gui", action="store_true",
                        help="启动图形化动画界面（电梯井道实时仿真）")
    args = parser.parse_args()

    if args.gui:
        from visual_gui import launch_gui
        launch_gui(total_floors=args.floors, duration=args.duration, seed=args.seed,
                   rate=args.rate, abandon=args.abandon)
        return

    print("=" * 56)
    print("       多功能电梯智能呼梯仿真系统（阶段1：基础仿真）")
    print("=" * 56)
    print(f"楼层数={args.floors}  客流时长={args.duration}s  "
          f"随机种子={args.seed}")
    print(f"乘客产生概率={args.rate}  放弃概率={args.abandon}")
    print("-" * 56)

    sim = Simulation(
        total_floors=args.floors,
        duration=args.duration,
        seed=args.seed,
        arrival_rate=args.rate,
        abandon_probability=args.abandon,
        print_event=not args.no_log,
    )
    report = sim.run()
    report.print_report()


if __name__ == "__main__":
    main()
