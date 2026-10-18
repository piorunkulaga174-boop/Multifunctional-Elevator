# -*- coding: utf-8 -*-
"""
电梯仿真 3D 可视化界面—— 基于 Python 标准库 tkinter，无需安装任何第三方包。

画面内容：
    左侧：电梯井道剖面动画（轿厢上下移动、两扇门开关、候梯小人、
          上下行呼梯灯、轿内目标楼层标记），实时刷新；
    右侧：运行控制、实时数据面板、事件日志。

启动方式：
    python visual_gui.py
    或  python main.py --gui
"""

# Windows 高 DPI 缩放适配：必须在创建 Tk 窗口前调用，
# 否则系统缩放（125%/150%/160%）会导致界面内容被截断或模糊。
try:
    from ctypes import windll
    try:
        windll.shcore.SetProcessDpiAwareness(1)   # Win8.1+ 按系统DPI感知
    except Exception:
        windll.user32.SetProcessDPIAware()        # 旧版系统兜底
except Exception:
    pass

import tkinter as tk
from tkinter import ttk
from collections import defaultdict

import config
from elevator_sim.elevator import ElevatorState
from elevator_sim.passenger import PassengerStatus
from elevator_sim.simulation import Simulation
from elevator_sim.scene3d import ElevatorScene3D

# ---------------- 画面基准常量（96 DPI 下，实际按系统缩放系数 S 放大） ----------------
FLOOR_H = 56           # 每层像素高度
TOP_PAD = 30
BOTTOM_PAD = 30
CANVAS_W = 620
SHAFT_X1, SHAFT_X2 = 60, 170     # 井道左右边界
CAR_W, CAR_H = 94, 48            # 轿厢宽高
WAIT_X0 = 250                    # 候梯区起点 x
PERSON_D = 16                    # 候梯小人直径
PERSON_GAP = 20

# 配色
C_BG = "#f5f6f8"
C_SHAFT = "#37474f"
C_FLOOR_LINE = "#b0bec5"
C_CAR = "#4a90d9"
C_CAR_EDGE = "#1f4e79"
C_DOOR = "#263238"
C_UP = "#ef6c00"      # 上行色（橙）
C_DOWN = "#1565c0"    # 下行色（蓝）
C_LAMP_OFF = "#cfd8dc"


class ElevatorGUI:
    def __init__(self, root: tk.Tk,
                 total_floors: int, duration: int, seed: int,
                 rate: float, abandon: float):
        self.root = root
        self.total_floors = total_floors
        self.init_duration = duration
        self.init_seed = seed
        self.init_rate = rate
        self.init_abandon = abandon

        # 系统缩放系数（125% 缩放时约 1.25，160% 时约 1.67）
        self.S = float(root.tk.call("tk", "scaling"))

        # 缩放后的画面尺寸
        self.floor_h = int(FLOOR_H * self.S)
        self.top_pad = int(TOP_PAD * self.S)
        self.bottom_pad = int(BOTTOM_PAD * self.S)
        self.canvas_w = int(CANVAS_W * self.S)
        self.canvas_h = (self.top_pad + total_floors * self.floor_h
                         + self.bottom_pad)
        self.shaft_x1 = int(SHAFT_X1 * self.S)
        self.shaft_x2 = int(SHAFT_X2 * self.S)
        self.car_w = int(CAR_W * self.S)
        self.car_h = int(CAR_H * self.S)
        self.wait_x0 = int(WAIT_X0 * self.S)
        self.person_d = int(PERSON_D * self.S)
        self.person_gap = int(PERSON_GAP * self.S)

        # 动画/调度状态
        self.running = False
        self.tick_ms = 300
        self.anim_bank = 0
        self.finished = False

        self._build_ui()
        self._fit_window()
        self.reset_sim()
        self.root.after(80, self._loop)

    def px(self, v):
        """基准像素 -> 按系统缩放后的物理像素。"""
        return int(v * self.S)

    def font(self, size, bold=False, family="微软雅黑"):
        return (family, max(1, int(size * self.S)),
                "bold" if bold else "normal")

    # ==================== 界面构建 ====================
    def _build_ui(self):
        self.root.title("多功能电梯智能呼梯仿真系统 —— 3D 仿真")
        self.root.resizable(True, True)

        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=tk.BOTH, expand=True)

        # ---------- 左侧：井道动画 ----------
        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.Y)
        self.canvas = tk.Canvas(left, width=self.canvas_w, height=self.canvas_h,
                                bg=C_BG, highlightthickness=1,
                                highlightbackground="#90a4ae")
        self.canvas.pack()
        # 3D 呈现层只读取仿真状态，不会修改任何调度规则或配置参数。
        self.scene = ElevatorScene3D(self.canvas, self.S, self.total_floors, self.font)
        self.canvas_w = self.scene.width
        self.canvas_h = self.scene.height

        # ---------- 右侧：控制面板 ----------
        right = ttk.Frame(main, padding=(10, 0, 0, 0))
        right.pack(side=tk.LEFT, fill=tk.Y)
        self.right_frame = right

        # 参数区
        param_box = ttk.LabelFrame(right, text="仿真参数（重置后生效）", padding=8)
        param_box.pack(fill=tk.X)
        ttk.Label(param_box, text="客流时长(秒):").grid(row=0, column=0, sticky="w")
        self.var_duration = tk.StringVar(value=str(self.init_duration))
        ttk.Entry(param_box, textvariable=self.var_duration, width=8).grid(row=0, column=1)
        ttk.Label(param_box, text="随机种子:").grid(row=0, column=2, sticky="w", padx=(10, 0))
        self.var_seed = tk.StringVar(value=str(self.init_seed))
        ttk.Entry(param_box, textvariable=self.var_seed, width=8).grid(row=0, column=3)
        ttk.Label(param_box, text="乘客概率:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.var_rate = tk.StringVar(value=str(self.init_rate))
        ttk.Entry(param_box, textvariable=self.var_rate, width=8).grid(row=1, column=1, pady=(6, 0))
        ttk.Label(param_box, text="放弃概率:").grid(row=1, column=2, sticky="w", padx=(10, 0), pady=(6, 0))
        self.var_abandon = tk.StringVar(value=str(self.init_abandon))
        ttk.Entry(param_box, textvariable=self.var_abandon, width=8).grid(row=1, column=3, pady=(6, 0))

        # 控制区
        ctrl_box = ttk.LabelFrame(right, text="运行控制", padding=8)
        ctrl_box.pack(fill=tk.X, pady=(8, 0))
        self.btn_run = ttk.Button(ctrl_box, text="▶ 开始", command=self.toggle_run)
        self.btn_run.grid(row=0, column=0, padx=4)
        ttk.Button(ctrl_box, text="↻ 重置", command=self.reset_sim).grid(row=0, column=1, padx=4)
        ttk.Label(ctrl_box, text="速度:").grid(row=0, column=2, padx=(16, 2))
        self.var_speed = tk.StringVar(value="1x")
        speed = ttk.Combobox(ctrl_box, textvariable=self.var_speed, width=5,
                             values=["0.5x", "1x", "2x", "4x"], state="readonly")
        speed.grid(row=0, column=3)
        speed.bind("<<ComboboxSelected>>", lambda e: self._apply_speed())

        # 仅切换观察相机，不影响仿真逻辑、随机种子或系统配置。
        ttk.Label(ctrl_box, text="3D视角:").grid(row=1, column=0, padx=(4, 2), pady=(7, 0))
        self.var_view = tk.StringVar(value="透视")
        view = ttk.Combobox(ctrl_box, textvariable=self.var_view, width=8,
                            values=["透视", "左前", "正视"], state="readonly")
        view.grid(row=1, column=1, columnspan=2, sticky="w", pady=(7, 0))
        view.bind("<<ComboboxSelected>>", lambda e: self.scene.set_view(self.var_view.get()))

        # 数据面板
        data_box = ttk.LabelFrame(right, text="实时数据", padding=8)
        data_box.pack(fill=tk.X, pady=(8, 0))
        self.var_data = {}
        rows = [
            ("time", "仿真时间"), ("phase", "运行阶段"),
            ("state", "电梯状态"), ("floor", "当前楼层"),
            ("car_n", "轿厢人数"), ("wait_n", "候梯人数"),
            ("load", "当前载重"), ("load_rate", "载重率"),
            ("total", "总乘客数"), ("done", "完成行程"),
            ("abandon", "放弃离开"), ("stops", "总停站"),
            ("empty", "空停次数"), ("empty_rate", "空停率"),
            ("radar", "雷达取消"), ("overload", "超载次数"),
            ("anti_pinch", "防夹重开"), ("avg_wait", "平均等待"),
        ]
        for i, (key, label) in enumerate(rows):
            r, c = divmod(i, 2)
            ttk.Label(data_box, text=label + ":").grid(row=r, column=c * 2,
                                                       sticky="w", padx=(0, 2), pady=1)
            v = tk.StringVar(value="-")
            ttk.Label(data_box, textvariable=v, width=9,
                      foreground="#1f4e79", font=self.font(9, bold=True)
                      ).grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 8), pady=1)
            self.var_data[key] = v

        # 事件日志
        log_box = ttk.LabelFrame(right, text="事件日志", padding=4)
        log_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.log_text = tk.Text(log_box, width=38, height=14, state=tk.DISABLED,
                                font=("Consolas", max(1, int(9 * self.S))),
                                bg="#ffffff", wrap=tk.NONE)
        scroll = ttk.Scrollbar(log_box, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _fit_window(self):
        """根据左侧画面与右侧面板的实际需求尺寸设置窗口。"""
        self.root.update_idletasks()
        req_w = self.canvas_w + self.right_frame.winfo_reqwidth() + 180
        req_h = max(self.canvas_h, self.right_frame.winfo_reqheight()) + 40
        self.root.geometry(f"{req_w}x{req_h}")
        self.root.minsize(req_w, req_h)

    # ==================== 仿真控制 ====================
    def reset_sim(self):
        try:
            duration = int(self.var_duration.get())
            seed = int(self.var_seed.get())
            rate = float(self.var_rate.get())
            abandon = float(self.var_abandon.get())
        except (ValueError, AttributeError):
            duration, seed, rate, abandon = self.init_duration, self.init_seed, \
                self.init_rate, self.init_abandon

        self.sim = Simulation(
            total_floors=self.total_floors,
            duration=duration, seed=seed,
            arrival_rate=rate, abandon_probability=abandon,
            print_event=False, print_tick=False,
        )
        self.running = False
        self.finished = False
        self.anim_bank = 0
        self.btn_run.configure(text="▶ 开始")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self._log("仿真已重置，点击「开始」运行。")
        self._redraw()
        self._update_stats()

    def toggle_run(self):
        if self.finished:
            return
        self.running = not self.running
        self.btn_run.configure(text="⏸ 暂停" if self.running else "▶ 继续")

    def _apply_speed(self):
        mapping = {"0.5x": 600, "1x": 300, "2x": 150, "4x": 60}
        self.tick_ms = mapping.get(self.var_speed.get(), 300)

    # ==================== 主循环 ====================
    def _loop(self):
        if self.running and not self.finished:
            self.anim_bank += 80
            while self.anim_bank >= self.tick_ms:
                self.anim_bank -= self.tick_ms
                ev = self.sim.step()
                self._handle_events(ev)
                if self.sim.is_finished():
                    self.finished = True
                    self.running = False
                    self.btn_run.configure(text="■ 已结束")
                    self._show_final_report()
                    break
                if self.sim.now >= self.sim.max_ticks:
                    self.finished = True
                    self.running = False
                    break
        self._redraw()
        self._update_stats()
        self.root.after(80, self._loop)

    def _handle_events(self, ev):
        for p in ev["new_call"]:
            d = "上行" if p.direction == 1 else "下行"
            tip = "（可能放弃）" if p.abandon_time else ""
            self._log(f"{p.origin}F呼梯{d}→{p.target}F #{p.pid}{tip}")
        for p in ev["abandoned"]:
            self._log(f"#{p.pid} 在{p.origin}F放弃离开")
        for item in ev.get("radar_cancelled", []):
            d = "上行" if item["direction"] == 1 else "下行"
            self._log(f"📡 {item['floor']}F{d}呼梯 门前无人 自动取消")
        if ev.get("overload"):
            self._log(f"⚠ 轿厢超载！保持开门")
        for p in ev.get("refused", []):
            self._log(f"⛔ #{p.pid} {p.origin}F被拒入（超载）")
        if ev.get("anti_pinch_reopen"):
            self._log(f"🛡️ 防夹触发！检测到闯入，重新开门")
        floor = ev["open_at"]
        if floor is not None:
            for p in ev["leavers"]:
                self._log(f"#{p.pid} 到达{floor}F出厢")
            for p in ev["boarders"]:
                self._log(f"#{p.pid} {floor}F进厢→{p.target}F")
            if ev["empty_stop"]:
                self._log(f"★ {floor}F空停（无人进出）")

    def _show_final_report(self):
        r = self.sim._build_report()
        self._log("=" * 34)
        self._log("仿真结束，最终统计：")
        self._log(f"总乘客 {r.total_passengers}｜完成 {r.completed_passengers}"
                  f"｜放弃 {r.abandoned_passengers}")
        self._log(f"停站 {r.total_stops}｜空停 {r.empty_stops}"
                  f"（{r.empty_stop_rate:.1%}）")
        self._log(f"雷达自动取消 {r.radar_cancellations} 次")
        self._log(f"超载 {r.overload_count} 次（累计 {r.overload_duration}s）")
        self._log(f"防夹重开 {r.anti_pinch_reopens} 次")
        self._log(f"平均等待 {r.avg_wait_time:.1f}s｜"
                  f"平均全程 {r.avg_travel_time:.1f}s")

    # ==================== 日志 ====================
    def _log(self, text):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{self.sim.now:>4}s] {text}\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 400:
            self.log_text.delete("1.0", f"{lines - 400}.0")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ==================== 坐标换算 ====================
    def floor_center_y(self, floor: float) -> float:
        return self.top_pad + (self.total_floors - floor) * self.floor_h + self.floor_h / 2

    def floor_top_y(self, floor: int) -> float:
        return self.top_pad + (self.total_floors - floor) * self.floor_h

    # ==================== 画面绘制 ====================
    def _redraw(self):
        """Render the current simulation snapshot in the independent 3D scene."""
        self.scene.render(self.sim)

    def _redraw_legacy_2d(self):
        """Previous 2D renderer retained temporarily as an internal reference."""
        cv = self.canvas
        cv.delete("all")
        e = self.sim.elevator

        # 1. 楼层背景、楼层号、层线
        for f in range(1, self.total_floors + 1):
            y_top = self.floor_top_y(f)
            y_c = self.floor_center_y(f)
            cv.create_rectangle(self.shaft_x1, y_top,
                                self.canvas_w - self.px(8), y_top + self.floor_h,
                                fill="#ffffff", outline=C_FLOOR_LINE)
            cv.create_text(self.px(30), y_c, text=f"{f}F",
                           font=self.font(10, bold=True), fill="#455a64")
            cv.create_line(self.shaft_x1, y_top, self.shaft_x1, y_top + self.floor_h,
                           fill=C_SHAFT, width=2)
            cv.create_line(self.shaft_x2, y_top, self.shaft_x2, y_top + self.floor_h,
                           fill=C_SHAFT, width=2)
            # 呼梯灯（上/下三角）
            self._draw_lamp(self.px(185), y_c - self.px(9), f in e.hall_up, up=True)
            self._draw_lamp(self.px(185), y_c + self.px(11), f in e.hall_down, up=False)
        # 井道上下边界
        cv.create_line(self.shaft_x1, self.top_pad, self.shaft_x2, self.top_pad,
                       fill=C_SHAFT, width=2)
        cv.create_line(self.shaft_x1, self.canvas_h - self.bottom_pad,
                       self.shaft_x2, self.canvas_h - self.bottom_pad,
                       fill=C_SHAFT, width=2)

        # 2. 候梯小人（按楼层分组，方向决定颜色）
        groups = defaultdict(list)
        for p in self.sim.passengers:
            if p.status == PassengerStatus.WAITING:
                groups[p.origin].append(p)
        for f, plist in groups.items():
            y_c = self.floor_center_y(f)
            for i, p in enumerate(plist):
                x = self.wait_x0 + (i % 10) * self.person_gap
                y = y_c - self.person_d / 2
                d = self.person_d
                color = C_UP if p.direction == 1 else C_DOWN
                cv.create_oval(x, y, x + d, y + d, fill=color,
                               outline="white", width=1)
                cv.create_text(x + d / 2, y + d / 2, text=str(p.pid),
                               fill="white", font=("Consolas",
                                                   max(1, int(7 * self.S)), "bold"))

        # 2.5 阶段2：毫米波雷达状态（门前有人/无人、无人计时条、自动取消标记）
        for f in range(1, self.total_floors + 1):
            has_call = (f in e.hall_up) or (f in e.hall_down)
            if not has_call:
                continue
            rs = self.sim.radar.get_radar_state(f)
            y_c = self.floor_center_y(f)
            # 雷达指示灯：绿色=有人，红色=无人
            radar_x = self.px(210)
            if rs["present"]:
                cv.create_oval(radar_x, y_c - self.px(5),
                               radar_x + self.px(10), y_c + self.px(5),
                               fill="#4caf50", outline="#2e7d32", width=1)
            else:
                cv.create_oval(radar_x, y_c - self.px(5),
                               radar_x + self.px(10), y_c + self.px(5),
                               fill="#e53935", outline="#b71c1c", width=1)
                # 无人计时进度条（达到阈值即自动取消）
                bar_w = self.px(30)
                bar_x = radar_x + self.px(14)
                frac = min(1.0, rs["empty_duration"] / rs["empty_seconds"])
                cv.create_rectangle(bar_x, y_c - self.px(3),
                                    bar_x + bar_w, y_c + self.px(3),
                                    fill="#eceff1", outline="#b0bec5")
                cv.create_rectangle(bar_x, y_c - self.px(3),
                                    bar_x + int(bar_w * frac), y_c + self.px(3),
                                    fill="#ff9800", outline="")
                if frac >= 1.0:
                    cv.create_text(bar_x + bar_w + self.px(8), y_c,
                                   text="✕取消", fill="#e53935",
                                   font=self.font(8, bold=True))

        # 3. 轿内目标楼层标记（井道左侧小方块）
        for tf in e.car_calls:
            y = self.floor_center_y(tf)
            cv.create_rectangle(self.px(44), y - self.px(7),
                                self.px(56), y + self.px(7),
                                fill=C_CAR, outline=C_CAR_EDGE)

        # 4. 轿厢（含移动、开门动画、内部人数）
        cy = self.floor_center_y(e.visual_position)
        x1, x2 = self.shaft_x1 + self.px(8), self.shaft_x2 - self.px(8)
        y1, y2 = cy - self.car_h / 2, cy + self.car_h / 2
        cv.create_rectangle(x1, y1, x2, y2, fill=C_CAR, outline=C_CAR_EDGE, width=2)
        # 两扇门：按开门度向两侧滑动
        frac = e.door_open_fraction
        door_w = (x2 - x1) / 2
        slide = door_w * frac * 0.92
        cv.create_rectangle(x1, y1 + 2, x1 + door_w - slide, y2 - 2,
                            fill=C_DOOR, outline="")
        cv.create_rectangle(x1 + door_w + slide, y1 + 2, x2, y2 - 2,
                            fill=C_DOOR, outline="")
        # 阶段4：关门过程中显示防夹检测区域（门前红外扫描线）
        if e.state == ElevatorState.CLOSING:
            scan_y = y1 - self.px(3)
            cv.create_line(x1 - self.px(6), scan_y, x2 + self.px(6), scan_y,
                           fill="#4caf50", width=2, dash=(4, 2))
            cv.create_text((x1 + x2) / 2, scan_y - self.px(8),
                           text="🛡 防夹监测中", fill="#2e7d32",
                           font=self.font(7, bold=True))
            # 阶段4：显示门前正在接近的行人（未按按钮的人，从远处走来）
            peds = self.sim.door_safety.get_pedestrians(e.current_floor)
            if peds:
                ped_y = cy - self.person_d / 2
                # 行人移动范围：从远处(x2+60px)到门口(x2+5px)
                far_x = x2 + self.px(55)
                near_x = x2 + self.px(5)
                for i, ped in enumerate(peds[:3]):
                    # 根据接近进度计算x坐标（从远到近）
                    px = far_x + (near_x - far_x) * ped.progress
                    # 到达门口时变红警告，还在走来时橙色
                    color = "#ff5722" if ped.at_door else "#ff9800"
                    outline = "#bf360c" if ped.at_door else "#e65100"
                    cv.create_oval(px, ped_y, px + self.person_d,
                                   ped_y + self.person_d,
                                   fill=color, outline=outline, width=2)
                    cv.create_text(px + self.person_d / 2, ped_y + self.person_d / 2,
                                   text="🚶", fill="white",
                                   font=self.font(8, bold=True))
                    # 行人之间错开y位置，避免重叠
                    ped_y += self.px(2)
                # 状态提示
                if any(p.at_door for p in peds):
                    cv.create_text((x1 + x2) / 2, y1 - self.px(20),
                                   text="⚠ 有人到门口！", fill="#ff5722",
                                   font=self.font(8, bold=True))
                else:
                    cv.create_text((x1 + x2) / 2, y1 - self.px(20),
                                   text=f"🚶 {len(peds)}人正在接近...", fill="#e65100",
                                   font=self.font(7, bold=True))
        # 阶段4修复：防夹触发闪烁（刚重开时）
        if (e.state == ElevatorState.OPENING
                and self.sim.door_safety.last_reopen_floor == e.current_floor):
            flash = (self.sim.now // 1) % 2 == 0
            if flash:
                cv.create_rectangle(x1 - 3, y1 - 3, x2 + 3, y2 + 3,
                                    outline="#ff5722", width=3)
                cv.create_text((x1 + x2) / 2, y1 - self.px(14),
                               text="⚠ 防夹重开", fill="#ff5722",
                               font=self.font(8, bold=True))
        # 阶段4修复：开门延长提示（有新乘客来时门保持打开）
        if e.state == ElevatorState.OPEN and e._hold_timer == 0:
            cv.create_text((x1 + x2) / 2, y1 - self.px(14),
                           text="⏳ 开门延长（有人来）", fill="#1565c0",
                           font=self.font(7, bold=True))
        # 轿厢内人数
        car_n = sum(1 for p in self.sim.passengers
                    if p.status == PassengerStatus.IN_CAR)
        cv.create_text((x1 + x2) / 2, cy, text=str(car_n),
                       fill="white", font=self.font(14, bold=True))

        # 阶段3：轿厢载重条（底部）+ 超载报警
        lc = self.sim.load_cell
        load_ratio = min(1.2, lc.load_ratio)
        bar_x1 = x1 + self.px(4)
        bar_x2 = x2 - self.px(4)
        bar_y = y2 - self.px(6)
        bar_h = self.px(4)
        cv.create_rectangle(bar_x1, bar_y, bar_x2, bar_y + bar_h,
                            fill="#37474f", outline="")
        load_color = "#4caf50" if load_ratio < 0.8 else (
            "#ff9800" if load_ratio < 1.0 else "#e53935")
        cv.create_rectangle(bar_x1, bar_y,
                            bar_x1 + int((bar_x2 - bar_x1) * min(1.0, load_ratio)),
                            bar_y + bar_h, fill=load_color, outline="")
        if lc.overload:
            # 超载报警：红色边框闪烁 + 文字
            flash = (self.sim.now // 1) % 2 == 0
            if flash:
                cv.create_rectangle(x1 - 2, y1 - 2, x2 + 2, y2 + 2,
                                    outline="#e53935", width=3)
            cv.create_text((x1 + x2) / 2, y1 - self.px(14),
                           text="⚠ 超载", fill="#e53935",
                           font=self.font(9, bold=True))

        # 轿厢顶部方向箭头
        arrow = "▲" if e.direction == 1 else "▼"
        arrow_color = C_UP if e.direction == 1 else C_DOWN
        if e.state in (ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN):
            cv.create_text((x1 + x2) / 2, y1 - self.px(10), text=arrow,
                           fill=arrow_color, font=self.font(11, bold=True))

    def _draw_lamp(self, x, y, on, up):
        d = self.px(11)
        color = (C_UP if up else C_DOWN) if on else C_LAMP_OFF
        if up:
            pts = [x, y - d / 2, x - d / 2, y + d / 2, x + d / 2, y + d / 2]
        else:
            pts = [x, y + d / 2, x - d / 2, y - d / 2, x + d / 2, y - d / 2]
        self.canvas.create_polygon(pts, fill=color, outline="#78909c")

    # ==================== 数据面板 ====================
    def _update_stats(self):
        e = self.sim.elevator
        ps = self.sim.passengers
        car_n = sum(1 for p in ps if p.status == PassengerStatus.IN_CAR)
        wait_n = sum(1 for p in ps if p.status == PassengerStatus.WAITING)
        done = [p for p in ps if p.status == PassengerStatus.DONE]
        wait_times = [p.wait_time for p in done if p.wait_time is not None]
        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0.0
        empty_stops = getattr(self.sim, "_empty_stop_hits", 0)

        if self.finished:
            phase = "已结束"
        elif self.sim.now < self.sim.duration:
            phase = "客流生成中"
        else:
            phase = "收尾服务中"
        direction = "上行" if e.direction == 1 else "下行"

        self.var_data["time"].set(f"{self.sim.now}s/{self.sim.duration}s")
        self.var_data["phase"].set(phase)
        self.var_data["state"].set(e.state_text())
        self.var_data["floor"].set(f"{e.current_floor}F {direction}")
        self.var_data["car_n"].set(str(car_n))
        self.var_data["wait_n"].set(str(wait_n))
        lc = self.sim.load_cell
        self.var_data["load"].set(f"{lc.current_load_kg:.0f}kg")
        self.var_data["load_rate"].set(f"{lc.load_ratio:.0%}")
        self.var_data["total"].set(str(len(ps)))
        self.var_data["done"].set(str(len(done)))
        self.var_data["abandon"].set(
            str(sum(1 for p in ps if p.status == PassengerStatus.ABANDONED)))
        self.var_data["stops"].set(str(e.stop_count))
        self.var_data["empty"].set(str(empty_stops))
        self.var_data["empty_rate"].set(
            f"{(empty_stops / e.stop_count):.1%}" if e.stop_count else "0.0%")
        self.var_data["radar"].set(str(self.sim.radar.auto_cancel_count))
        self.var_data["overload"].set(str(self.sim.load_cell.overload_count))
        self.var_data["anti_pinch"].set(str(self.sim.door_safety.reopen_count))
        self.var_data["avg_wait"].set(f"{avg_wait:.1f}s")


def launch_gui(total_floors=config.TOTAL_FLOORS,
               duration=config.SIMULATION_DURATION,
               seed=config.RANDOM_SEED,
               rate=config.CALL_ARRIVAL_RATE,
               abandon=config.ABANDON_PROBABILITY):
    root = tk.Tk()
    ElevatorGUI(root, total_floors=total_floors, duration=duration, seed=seed,
                rate=rate, abandon=abandon)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
