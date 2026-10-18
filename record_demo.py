# -*- coding: utf-8 -*-
"""自动录制3D仿真演示：直接创建GUI实例、自动开始、截取静态图、录制GIF。"""
import sys
import os
import time
import threading
import tkinter as tk
import ctypes
from ctypes import wintypes
from PIL import ImageGrab, Image

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

import config
from visual_gui import ElevatorGUI

OUTPUT_DIR = os.path.join(PROJECT_DIR, "tests")
WINDOW_TITLE = "多功能电梯智能呼梯仿真系统 —— 3D 仿真"

user32 = ctypes.windll.user32
user32.FindWindowW.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]

frames = []
stop_capture = False


def capture_worker(gif_path, static_path, fps=8, gif_duration=6):
    """后台截图线程：先等运行起来，截静态图，再录GIF。"""
    global stop_capture

    # 等待GUI窗口出现并开始运行
    time.sleep(5)

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        print("截图线程：未找到窗口")
        return

    def grab():
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        bbox = (rect.left + 8, rect.top + 8, rect.right - 8, rect.bottom - 8)
        return ImageGrab.grab(bbox=bbox)

    # 截取静态图（此时电梯已运行）
    print("截取静态图...")
    static_img = grab()
    static_img.save(static_path)
    print(f"静态图已保存: {static_path}")

    # 录制GIF
    print(f"录制GIF ({gif_duration}s, {fps}fps)...")
    interval = 1.0 / fps
    for i in range(int(gif_duration * fps)):
        if stop_capture:
            break
        img = grab()
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        frames.append(img)
        time.sleep(interval)

    if frames:
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=int(interval * 1000),
            loop=0,
            optimize=True,
        )
        size_kb = os.path.getsize(gif_path) // 1024
        print(f"GIF已保存: {gif_path} ({len(frames)}帧, {size_kb}KB)")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    root = tk.Tk()
    gui = ElevatorGUI(
        root,
        total_floors=config.TOTAL_FLOORS,
        duration=300,
        seed=42,
        rate=0.15,
        abandon=0.2,
    )

    # 1.5秒后自动点击开始
    root.after(1500, gui.toggle_run)

    # 启动截图线程
    gif_path = os.path.join(OUTPUT_DIR, "demo_3d.gif")
    static_path = os.path.join(OUTPUT_DIR, "gui_3d.png")
    capture_thread = threading.Thread(
        target=capture_worker, args=(gif_path, static_path), daemon=True
    )
    capture_thread.start()

    # 18秒后自动关闭
    def close():
        global stop_capture
        stop_capture = True
        root.quit()
        root.destroy()

    root.after(18000, close)
    root.mainloop()

    capture_thread.join(timeout=5)
    print("录制完成")


if __name__ == "__main__":
    main()
