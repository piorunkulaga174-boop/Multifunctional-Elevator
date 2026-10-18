# -*- coding: utf-8 -*-
"""
阶段5：全系统联调与对照实验。

三组对照实验（相同客流、相同随机种子，仅功能开关不同）：
    A. 普通电梯：所有智能功能关闭
    B. 仅雷达优化：只开无人呼梯自动取消
    C. 全功能智能电梯：雷达+负重+防夹+开门延长 全开

每组运行 N 次不同随机种子的 600 秒仿真，取平均值。
输出：实验数据 CSV + 对比图表 PNG。
"""

import csv
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")  # 无GUI后端
import matplotlib.pyplot as plt
import numpy as np

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from elevator_sim.simulation import Simulation
from elevator_sim.scenario import generate_requests, scenario_document, scenario_hash


# ==================== 实验配置 ====================
NUM_ROUNDS = 10           # 每组实验重复次数
SIMULATION_DURATION = 600  # 每次仿真时长（秒）
ARRIVAL_RATE = 0.15       # 客流到达率
ABANDON_PROB = 0.20       # 乘客放弃概率
BASE_SEED = 42            # 基础随机种子

# 三组实验配置
EXPERIMENTS = [
    {
        "name": "普通电梯",
        "short": "普通",
        "radar_enabled": False,
        "load_cell_enabled": False,
        "anti_pinch_enabled": False,
        "hold_extension_enabled": False,
        "color": "#9e9e9e",
    },
    {
        "name": "仅雷达优化",
        "short": "仅雷达",
        "radar_enabled": True,
        "load_cell_enabled": False,
        "anti_pinch_enabled": False,
        "hold_extension_enabled": False,
        "color": "#42a5f5",
    },
    {
        "name": "全功能智能电梯",
        "short": "全功能",
        "radar_enabled": True,
        "load_cell_enabled": True,
        "anti_pinch_enabled": True,
        "hold_extension_enabled": True,
        "color": "#66bb6a",
    },
]

# 统计指标列表
METRICS = [
    ("total_passengers", "总乘客数"),
    ("completed_passengers", "完成行程数"),
    ("abandoned_passengers", "放弃乘梯数"),
    ("total_stops", "总停站次数"),
    ("empty_stops", "空停次数"),
    ("empty_stop_rate", "空停率(%)"),
    ("avg_wait_time", "平均等待时间(s)"),
    ("avg_total_time", "平均全程时间(s)"),
    ("max_wait_time", "最长等待时间(s)"),
    ("radar_cancellations", "雷达取消呼梯数"),
    ("overload_count", "超载发生次数"),
    ("anti_pinch_reopens", "防夹重开次数"),
]


def make_scenario(seed):
    return generate_requests(seed, duration=SIMULATION_DURATION,
                             arrival_rate=ARRIVAL_RATE,
                             abandon_probability=ABANDON_PROB)


def run_single_experiment(exp_config: dict, seed: int, requests=None) -> Dict:
    """运行单次仿真，返回指标字典。"""
    if exp_config.get("pedestrian_prob", 0):
        raise ValueError("paired experiments cannot add policy-dependent pedestrians; use the demos")
    requests = tuple(make_scenario(seed) if requests is None else requests)
    sim = Simulation(
        duration=SIMULATION_DURATION,
        seed=seed,
        arrival_rate=ARRIVAL_RATE,
        abandon_probability=ABANDON_PROB,
        print_event=False,
        print_tick=False,
        radar_enabled=exp_config["radar_enabled"],
        load_cell_enabled=exp_config["load_cell_enabled"],
        anti_pinch_enabled=exp_config["anti_pinch_enabled"],
        hold_extension_enabled=exp_config["hold_extension_enabled"],
        requests=requests,
    )
    # Performance comparison uses identical pre-generated demand. Incidental
    # pedestrian demonstrations belong to separate safety scenarios.
    sim.door_safety.pedestrian_prob = 0.0
    report = sim.run()
    if not sim.is_finished() or report.total_passengers != len(requests):
        raise RuntimeError("paired experiment did not finish with the frozen input")

    # 计算最长等待时间
    wait_times = [p.wait_time for p in sim.passengers
                  if p.status.name == "DONE" and p.wait_time is not None]
    max_wait = max(wait_times) if wait_times else 0

    return {
        "seed": seed,
        "scenario_sha256": scenario_hash(requests),
        "total_passengers": report.total_passengers,
        "completed_passengers": report.completed_passengers,
        "abandoned_passengers": report.abandoned_passengers,
        "total_stops": report.total_stops,
        "empty_stops": report.empty_stops,
        "empty_stop_rate": round(report.empty_stop_rate * 100, 2),
        "avg_wait_time": round(report.avg_wait_time, 2),
        "avg_total_time": round(report.avg_travel_time, 2),
        "max_wait_time": round(max_wait, 2),
        "radar_cancellations": sim.radar.auto_cancel_count,
        "overload_count": sim.load_cell.overload_count,
        "anti_pinch_reopens": sim.door_safety.reopen_count,
    }


def run_experiment_group(exp_config: dict, scenarios=None) -> List[Dict]:
    """运行一组实验（多次不同种子），返回每次的结果列表。"""
    results = []
    for i in range(NUM_ROUNDS):
        seed = BASE_SEED + i
        print(f"  运行 {exp_config['name']} 第 {i+1}/{NUM_ROUNDS} 次 (seed={seed})...")
        result = run_single_experiment(exp_config, seed,
                                       None if scenarios is None else scenarios[seed])
        results.append(result)
    return results


def average_results(results: List[Dict]) -> Dict:
    """对多次实验结果取平均值。"""
    if not results:
        return {}
    avg = {}
    for key in results[0]:
        if key in ("seed", "scenario_sha256"):
            continue
        values = [r[key] for r in results]
        avg[key] = round(sum(values) / len(values), 2)
    return avg


def save_csv(all_results: Dict[str, List[Dict]], avg_results: Dict[str, Dict],
             output_dir=None):
    """保存实验数据到CSV。"""
    output_dir = str(output_dir or Path(__file__).parent / "experiments" / "paired_v1")
    os.makedirs(output_dir, exist_ok=True)

    # 1. 详细数据（每次实验）
    detail_path = os.path.join(output_dir, "experiment_detail.csv")
    with open(detail_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        header = ["实验组", "种子", "输入场景SHA256"] + [label for _, label in METRICS]
        writer.writerow(header)
        for exp_name, results in all_results.items():
            for r in results:
                row = [exp_name, r["seed"], r["scenario_sha256"]] + [r[key] for key, _ in METRICS]
                writer.writerow(row)
    print(f"详细数据已保存: {detail_path}")

    # 2. 汇总数据（平均值）
    summary_path = os.path.join(output_dir, "experiment_summary.csv")
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        header = ["实验组"] + [label for _, label in METRICS]
        writer.writerow(header)
        for exp_name, avg in avg_results.items():
            row = [exp_name] + [avg.get(key, 0) for key, _ in METRICS]
            writer.writerow(row)
    print(f"汇总数据已保存: {summary_path}")

    return output_dir


def plot_comparison(avg_results: Dict[str, Dict], output_dir: str):
    """生成对比图表。"""
    plt.rcParams["font.sans-serif"] = ["SimHei", "Microsoft YaHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    exp_names = list(avg_results.keys())
    colors = [exp["color"] for exp in EXPERIMENTS]

    # 图1：核心效率指标对比
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("电梯智能化功能效果对比实验（10次仿真平均值）", fontsize=16, fontweight="bold")

    # 平均等待时间
    ax = axes[0, 0]
    values = [avg_results[n]["avg_wait_time"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("平均等待时间", fontsize=13)
    ax.set_ylabel("秒")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                f"{v:.1f}s", ha="center", fontsize=11)

    # 空停率
    ax = axes[0, 1]
    values = [avg_results[n]["empty_stop_rate"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("空停率", fontsize=13)
    ax.set_ylabel("%")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f"{v:.1f}%", ha="center", fontsize=11)

    # 完成行程数
    ax = axes[1, 0]
    values = [avg_results[n]["completed_passengers"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("完成行程数（含客流结束后的收尾）", fontsize=13)
    ax.set_ylabel("人")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{v:.0f}", ha="center", fontsize=11)

    # 放弃乘梯数
    ax = axes[1, 1]
    values = [avg_results[n]["abandoned_passengers"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("放弃乘梯人数", fontsize=13)
    ax.set_ylabel("人")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                f"{v:.0f}", ha="center", fontsize=11)

    plt.tight_layout()
    chart1_path = os.path.join(output_dir, "chart_efficiency.png")
    plt.savefig(chart1_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"效率对比图已保存: {chart1_path}")

    # 图2：安全与智能功能指标
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle("智能功能运行指标统计", fontsize=16, fontweight="bold")

    # 雷达取消呼梯数
    ax = axes[0]
    values = [avg_results[n]["radar_cancellations"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("雷达自动取消呼梯次数", fontsize=13)
    ax.set_ylabel("次")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{v:.1f}", ha="center", fontsize=11)

    # 防夹重开次数
    ax = axes[1]
    values = [avg_results[n]["anti_pinch_reopens"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("防夹重开次数（仿真触发）", fontsize=13)
    ax.set_ylabel("次")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                f"{v:.1f}", ha="center", fontsize=11)

    # 超载发生次数
    ax = axes[2]
    values = [avg_results[n]["overload_count"] for n in exp_names]
    bars = ax.bar(exp_names, values, color=colors)
    ax.set_title("超载发生次数", fontsize=13)
    ax.set_ylabel("次")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f"{v:.1f}", ha="center", fontsize=11)

    plt.tight_layout()
    chart2_path = os.path.join(output_dir, "chart_safety.png")
    plt.savefig(chart2_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"安全指标图已保存: {chart2_path}")

    return chart1_path, chart2_path


def print_summary(avg_results: Dict[str, Dict]):
    """打印实验汇总。"""
    print("\n" + "=" * 70)
    print("  阶段5对照实验汇总（10次仿真平均值）")
    print("=" * 70)
    header = f"{'指标':<18}" + "".join(f"{n:<16}" for n in avg_results)
    print(header)
    print("-" * 70)
    for key, label in METRICS:
        row = f"{label:<18}"
        for n in avg_results:
            row += f"{avg_results[n].get(key, 0):<16}"
        print(row)
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="相同冻结客流的配对实验")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "experiments" / "paired_v1")
    args = parser.parse_args()
    print("=" * 60)
    print("  阶段5：全系统联调与对照实验")
    print(f"  每组 {NUM_ROUNDS} 次仿真，每次 {SIMULATION_DURATION} 秒")
    print("=" * 60)

    all_results = {}
    avg_results = {}
    scenarios = {BASE_SEED + i: make_scenario(BASE_SEED + i)
                 for i in range(NUM_ROUNDS)}

    for exp in EXPERIMENTS:
        print(f"\n>>> 实验组：{exp['name']}")
        results = run_experiment_group(exp, scenarios)
        all_results[exp["name"]] = results
        avg_results[exp["name"]] = average_results(results)

    # 打印汇总
    print_summary(avg_results)

    # 保存CSV
    for i in range(NUM_ROUNDS):
        hashes = {rows[i]["scenario_sha256"] for rows in all_results.values()}
        if len(hashes) != 1:
            raise RuntimeError("input mismatch between experiment groups")
    output_dir = save_csv(all_results, avg_results, args.output)
    input_dir = Path(output_dir) / "inputs"
    input_dir.mkdir(exist_ok=True)
    for seed, requests in scenarios.items():
        document = scenario_document(requests)
        document.update(seed=seed, duration=SIMULATION_DURATION,
                        sha256=scenario_hash(requests))
        (input_dir / f"seed_{seed}.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成图表
    chart1, chart2 = plot_comparison(avg_results, output_dir)

    print("\n实验完成！产物：")
    print(f"  - 实验数据目录: {output_dir}")
    print(f"  - 效率对比图: {chart1}")
    print(f"  - 安全指标图: {chart2}")


if __name__ == "__main__":
    main()
