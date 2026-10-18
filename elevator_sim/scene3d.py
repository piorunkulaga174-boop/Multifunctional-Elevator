# -*- coding: utf-8 -*-
"""Tkinter Canvas based 3D presentation layer for the elevator simulator.

The simulation is still a discrete-event model.  This module deliberately owns
only projection and drawing: it must never change elevator, passenger, or
configuration state.  Keeping the renderer separate makes the visual upgrade
safe to use with the existing simulation and its deterministic tests.
"""

from collections import defaultdict

from elevator_sim.elevator import ElevatorState
from elevator_sim.passenger import PassengerStatus


class ElevatorScene3D:
    """Render one elevator shaft as a lightweight perspective 3D scene.

    Tkinter has no native 3D API, so the scene uses a deterministic oblique
    projection.  It is intentionally dependency-free and runs anywhere the
    previous Tkinter interface ran.
    """

    BACKGROUND_TOP = "#09162b"
    BACKGROUND_BOTTOM = "#1d3557"
    FLOOR_FRONT = "#c9d6e2"
    FLOOR_SIDE = "#91a4b8"
    SHAFT = "#31475f"
    SHAFT_DARK = "#1a2a3c"
    CAR_FRONT = "#2574b8"
    CAR_SIDE = "#174c7a"
    CAR_TOP = "#5da9e8"

    def __init__(self, canvas, scale, total_floors, font_factory):
        self.canvas = canvas
        self.s = scale
        self.total_floors = total_floors
        self.font = font_factory
        self.view = "透视"
        self.width = int(720 * scale)
        self.height = int((112 + total_floors * 56) * scale)
        self.canvas.configure(width=self.width, height=self.height)

    def set_view(self, view):
        """Select a presentational camera angle; no model data is modified."""
        self.view = view

    def _layout(self):
        s = self.s
        # A cut-away building: the shaft is left, and the lobby runs to its
        # right.  The lift door is deliberately drawn on the shaft's right
        # face, so it always faces the people in the lobby.
        if self.view == "正视":
            dx, dy = int(34 * s), int(-4 * s)
        elif self.view == "左前":
            dx, dy = int(-58 * s), int(-34 * s)
        else:
            dx, dy = int(72 * s), int(-38 * s)
        return {
            "left": int(112 * s), "right": int(282 * s),
            "depth_x": dx, "depth_y": dy,
            "base": self.height - int(46 * s),
            "floor_h": int(52 * s),
            "platform_right": int(680 * s),
            "hall_left": int(282 * s) + dx,
        }

    def _floor_y(self, floor, layout):
        return layout["base"] - (floor - 1) * layout["floor_h"]

    def _poly(self, points, **kwargs):
        flat = [value for point in points for value in point]
        self.canvas.create_polygon(*flat, **kwargs)

    def _line(self, points, **kwargs):
        flat = [value for point in points for value in point]
        self.canvas.create_line(*flat, **kwargs)

    def _draw_background(self):
        """A small vertical gradient makes depth and bright safety signals legible."""
        bands = 22
        for i in range(bands):
            p = i / max(1, bands - 1)
            r = int(9 + (29 - 9) * p)
            g = int(22 + (53 - 22) * p)
            b = int(43 + (87 - 43) * p)
            color = f"#{r:02x}{g:02x}{b:02x}"
            y1 = i * self.height / bands
            y2 = (i + 1) * self.height / bands
            self.canvas.create_rectangle(0, y1, self.width, y2,
                                         fill=color, outline="")

    def _draw_structure(self, layout):
        left, right = layout["left"], layout["right"]
        dx, dy = layout["depth_x"], layout["depth_y"]
        base, floor_h = layout["base"], layout["floor_h"]
        top = base - (self.total_floors - 1) * floor_h - int(38 * self.s)

        hall_right = layout["platform_right"]
        # The dark rear wall, left elevator wall, and lobby wall create a
        # readable open building section instead of an isolated floating shaft.
        self._poly([(left + dx, top + dy), (hall_right + dx, top + dy),
                    (hall_right + dx, base + dy), (left + dx, base + dy)],
                   fill="#1b3248", outline="#54718b")
        self._poly([(left, top), (left + dx, top + dy),
                    (left + dx, base + dy), (left, base)],
                   fill="#12263a", outline="#6a849a")
        self._poly([(hall_right, top), (hall_right + dx, top + dy),
                    (hall_right + dx, base + dy), (hall_right, base)],
                   fill="#183149", outline="#5f7d95")

        for floor in range(1, self.total_floors + 1):
            y = self._floor_y(floor, layout)
            # Every storey is a full lobby slab, producing an architectural
            # cutaway and a shared plane for the lift door and its passengers.
            self._poly([(left - int(14 * self.s), y), (hall_right, y),
                        (hall_right + dx, y + dy),
                        (left - int(14 * self.s) + dx, y + dy)],
                       fill=self.FLOOR_FRONT, outline="#7890a6")
            self._poly([(left - int(14 * self.s), y), (hall_right, y),
                        (hall_right, y + int(6 * self.s)),
                        (left - int(14 * self.s), y + int(6 * self.s))],
                       fill="#91a9bd", outline="")
            self._line([(left, y), (left + dx, y + dy)], fill="#6c859d", width=1)
            self._line([(right, y), (right + dx, y + dy)], fill="#6c859d", width=1)
            self.canvas.create_text(int(54 * self.s), y - int(11 * self.s),
                                    text=f"{floor}F", fill="#dfeaf4",
                                    font=self.font(9, bold=True), anchor="w")

        self._line([(left, top), (left, base)], fill="#9ab1c6", width=max(1, int(2 * self.s)))
        self._line([(right, top), (right, base)], fill="#9ab1c6", width=max(1, int(2 * self.s)))
        self._line([(left + dx, top + dy), (left + dx, base + dy)], fill="#6e879e")
        self._line([(right + dx, top + dy), (right + dx, base + dy)], fill="#6e879e")
        self._line([(hall_right, top), (hall_right, base)], fill="#7190a8", width=max(1, int(self.s)))
        self.canvas.create_text(int(18 * self.s), int(18 * self.s), anchor="w",
                                text="仿真楼 · 3D 电梯大厅", fill="#ffffff",
                                font=self.font(13, bold=True))
        self.canvas.create_text(int(18 * self.s), int(40 * self.s), anchor="w",
                                text="轿厢门朝向候梯大厅 · 仅改变呈现层", fill="#a8c5dd",
                                font=self.font(8))

    def _draw_hall_panel(self, floor, elevator, layout):
        y = self._floor_y(floor, layout) + layout["depth_y"] - int(34 * self.s)
        x = layout["hall_left"] + int(12 * self.s)
        self.canvas.create_rectangle(x, y, x + int(20 * self.s), y + int(28 * self.s),
                                     fill="#152536", outline="#6d8ba5")
        up = "#ff9d18" if floor in elevator.hall_up else "#54687a"
        down = "#48a6ff" if floor in elevator.hall_down else "#54687a"
        self.canvas.create_polygon(x + int(10 * self.s), y + int(5 * self.s),
                                   x + int(5 * self.s), y + int(12 * self.s),
                                   x + int(15 * self.s), y + int(12 * self.s),
                                   fill=up, outline="")
        self.canvas.create_polygon(x + int(10 * self.s), y + int(23 * self.s),
                                   x + int(5 * self.s), y + int(16 * self.s),
                                   x + int(15 * self.s), y + int(16 * self.s),
                                   fill=down, outline="")

    def _draw_radar(self, floor, sim, layout):
        elevator = sim.elevator
        if floor not in elevator.hall_up and floor not in elevator.hall_down:
            return
        state = sim.radar.get_radar_state(floor)
        y = self._floor_y(floor, layout) + layout["depth_y"] - int(15 * self.s)
        x = layout["hall_left"] + int(48 * self.s)
        color = "#53d769" if state["present"] else "#ff5d5d"
        self.canvas.create_oval(x, y, x + int(11 * self.s), y + int(11 * self.s),
                                fill=color, outline="#ffffff")
        # Radar waves remain visible in depth, signalling the sensor state.
        for r in (8, 14):
            rr = int(r * self.s)
            self.canvas.create_arc(x - rr, y - rr, x + rr, y + rr,
                                   start=300, extent=120, style="arc",
                                   outline=color, width=max(1, int(self.s)))
        if not state["present"]:
            ratio = min(1.0, state["empty_duration"] / state["empty_seconds"])
            bar_x = x + int(21 * self.s)
            bar_w = int(26 * self.s)
            self.canvas.create_rectangle(bar_x, y + int(3 * self.s),
                                         bar_x + bar_w, y + int(8 * self.s),
                                         fill="#21384d", outline="#6d8ba5")
            self.canvas.create_rectangle(bar_x, y + int(3 * self.s),
                                         bar_x + int(bar_w * ratio), y + int(8 * self.s),
                                         fill="#ffb020", outline="")

    def _draw_person(self, x, ground_y, color, label, depth=0):
        """Draw a shaded, ground-contacted 3D avatar rather than a flat icon."""
        s = self.s
        shift_x, shift_y = depth * int(6 * s), depth * int(-3 * s)
        x += shift_x
        ground_y += shift_y
        head_r = max(3, int(5 * s))
        body_w, body_h = int(12 * s), int(16 * s)
        # Shadow establishes where a person stands on the 3D floor.
        self.canvas.create_oval(x - int(9 * s), ground_y - int(3 * s),
                                x + int(12 * s), ground_y + int(3 * s),
                                fill="#203242", outline="")
        # Rear body facet first, then the front face: a simple but visible volume.
        self._poly([(x + body_w // 2, ground_y - body_h),
                    (x + body_w // 2 + int(6 * s), ground_y - body_h - int(3 * s)),
                    (x + body_w // 2 + int(6 * s), ground_y - int(3 * s)),
                    (x + body_w // 2, ground_y)],
                   fill="#173d62", outline="#0c243c")
        self._poly([(x - body_w // 2, ground_y - body_h),
                    (x + body_w // 2, ground_y - body_h),
                    (x + body_w // 2, ground_y),
                    (x - body_w // 2, ground_y - int(3 * s))],
                   fill=color, outline="#15304b")
        self.canvas.create_oval(x - head_r, ground_y - body_h - 2 * head_r,
                                x + head_r, ground_y - body_h,
                                fill="#ffd4b8", outline="#8f5d4a")
        self.canvas.create_text(x, ground_y - body_h // 2,
                                text=str(label), fill="white",
                                font=("Consolas", max(5, int(6 * s)), "bold"))

    def _draw_waiting_people(self, sim, layout):
        groups = defaultdict(list)
        for passenger in sim.passengers:
            if passenger.status == PassengerStatus.WAITING:
                groups[passenger.origin].append(passenger)
        for floor, passengers in groups.items():
            # Waiting people share the same floor plane as the door threshold.
            y = self._floor_y(floor, layout) + layout["depth_y"]
            start = layout["hall_left"] + int(92 * self.s)
            for index, passenger in enumerate(passengers[:10]):
                col, row = index % 5, index // 5
                color = "#f28c28" if passenger.direction == 1 else "#267dcc"
                self._draw_person(start + col * int(28 * self.s),
                                  y - row * int(8 * self.s), color, passenger.pid,
                                  depth=col % 2 + row)

    def _draw_target_beacons(self, elevator, layout):
        for floor in elevator.car_calls:
            y = self._floor_y(floor, layout)
            x = layout["left"] - int(30 * self.s)
            self.canvas.create_oval(x, y - int(19 * self.s), x + int(13 * self.s),
                                    y - int(6 * self.s), fill="#69d8ff", outline="#ffffff")
            self.canvas.create_text(x + int(6 * self.s), y - int(13 * self.s),
                                    text="◆", fill="#12314d", font=self.font(6, bold=True))

    def _draw_car(self, sim, layout):
        elevator = sim.elevator
        s = self.s
        left, right = layout["left"] + int(12 * s), layout["right"] - int(12 * s)
        dx, dy = layout["depth_x"], layout["depth_y"]
        floor_y = self._floor_y(elevator.visual_position, layout)
        car_h = int(38 * s)
        top, bottom = floor_y - car_h, floor_y
        # Box: the right-hand plane is the *hall-facing elevator door*.  This
        # resolves the old mismatch where the people were beside a front-facing
        # door rather than standing at its threshold.
        self._poly([(right, top), (right + dx, top + dy),
                    (right + dx, bottom + dy), (right, bottom)],
                   fill="#0c2032", outline="#b8e3ff")
        self._poly([(left, top), (right, top), (right + dx, top + dy),
                    (left + dx, top + dy)], fill=self.CAR_TOP, outline="#a1d3ff")
        self.canvas.create_rectangle(left, top, right, bottom,
                                     fill=self.CAR_FRONT, outline="#c6e7ff",
                                     width=max(1, int(2 * s)))

        # The cut-away front is still visible as the solid cabin body.
        inset = int(3 * s)
        self.canvas.create_rectangle(left + inset, top + inset, right - inset, bottom - inset,
                                     fill="#1d5f99", outline="")

        # Door panels occupy the hall-facing side plane and physically slide
        # away from its midpoint.  The dark opening behind them makes the
        # distinction between car body and opening obvious.
        def door_point(t, y):
            return right + dx * t, y + dy * t

        def door_panel(t1, t2, fill):
            self._poly([door_point(t1, top), door_point(t2, top),
                        door_point(t2, bottom), door_point(t1, bottom)],
                       fill=fill, outline="#d5e9f6")

        opening = elevator.door_open_fraction
        left_end = 0.5 * (1.0 - opening)
        right_start = 0.5 * (1.0 + opening)
        door_panel(0.0, left_end, "#b9cbd8")
        door_panel(right_start, 1.0, "#91aabd")
        mid_x, mid_y = door_point(.5, top)
        self.canvas.create_text(mid_x, mid_y - int(10 * s), text="厅门",
                                fill="#e4f4ff", font=self.font(7, bold=True))

        in_car = [p for p in sim.passengers if p.status == PassengerStatus.IN_CAR]
        if elevator.door_open_fraction > 0.35:
            for index, passenger in enumerate(in_car[:5]):
                x, y = door_point(.24 + index * .12, bottom)
                self._draw_person(x, y - int(2 * s), "#7c5ce0", passenger.pid,
                                  depth=1)
        else:
            self.canvas.create_text((left + right) / 2, (top + bottom) / 2,
                                    text=str(len(in_car)), fill="white",
                                    font=self.font(14, bold=True))

        # Load strip, overload alarm and the direction indicator stay bound to model state.
        load = sim.load_cell
        ratio = min(1.0, load.load_ratio)
        bx1, bx2 = left + int(7 * s), right - int(7 * s)
        by = bottom - int(7 * s)
        self.canvas.create_rectangle(bx1, by, bx2, by + int(4 * s),
                                     fill="#0c1b29", outline="")
        load_color = "#55d77a" if ratio < .8 else "#ffb020" if ratio < 1 else "#ff5252"
        self.canvas.create_rectangle(bx1, by, bx1 + (bx2 - bx1) * ratio, by + int(4 * s),
                                     fill=load_color, outline="")
        if elevator.state in (ElevatorState.MOVING_UP, ElevatorState.MOVING_DOWN):
            marker = "▲" if elevator.direction == 1 else "▼"
            self.canvas.create_text((left + right) / 2, top - int(13 * s), text=marker,
                                    fill="#ffba49" if elevator.direction == 1 else "#65b5ff",
                                    font=self.font(11, bold=True))
        if load.overload:
            self.canvas.create_rectangle(left - int(3 * s), top - int(3 * s),
                                         right + int(3 * s), bottom + int(3 * s),
                                         outline="#ff4b4b", width=max(2, int(3 * s)))
            self.canvas.create_text((left + right) / 2, top - int(27 * s), text="⚠ 超载",
                                    fill="#ff7373", font=self.font(9, bold=True))

        self._draw_safety_overlay(sim, layout, left, right, top, bottom)

    def _draw_safety_overlay(self, sim, layout, left, right, top, bottom):
        elevator = sim.elevator
        s = self.s
        dx, dy = layout["depth_x"], layout["depth_y"]
        if elevator.state == ElevatorState.CLOSING:
            # The scan line lies across the hall-facing door, not above the
            # cab's front wall, so the safety feedback matches the passenger
            # approach path.
            self.canvas.create_line(right - int(5 * s), top - int(3 * s),
                                    right + dx + int(5 * s), top + dy - int(3 * s),
                                    fill="#63e58d", width=max(1, int(2 * s)), dash=(4, 2))
            self.canvas.create_text(right + dx / 2, top + dy - int(17 * s), text="防夹扫描中",
                                    fill="#79ef9e", font=self.font(7, bold=True))
            peds = sim.door_safety.get_pedestrians(elevator.current_floor)
            for index, pedestrian in enumerate(peds[:3]):
                x = (right + dx + int((66 - 42 * pedestrian.progress) * s)
                     + index * int(11 * s))
                color = "#ff5b48" if pedestrian.at_door else "#ffa028"
                self._draw_person(x, bottom + dy, color, "!", depth=index % 2)
        if (elevator.state == ElevatorState.OPENING and
                sim.door_safety.last_reopen_floor == elevator.current_floor):
            self.canvas.create_text(right + dx / 2, top + dy - int(19 * s), text="⚠ 防夹重开",
                                    fill="#ff795f", font=self.font(8, bold=True))

    def render(self, sim):
        self.canvas.delete("all")
        layout = self._layout()
        self._draw_background()
        self._draw_structure(layout)
        for floor in range(1, self.total_floors + 1):
            self._draw_hall_panel(floor, sim.elevator, layout)
            self._draw_radar(floor, sim, layout)
        self._draw_target_beacons(sim.elevator, layout)
        self._draw_waiting_people(sim, layout)
        self._draw_car(sim, layout)
