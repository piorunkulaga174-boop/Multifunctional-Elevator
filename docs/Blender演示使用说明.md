# Blender 单梯大厅与建筑剖面演示

两个 Blender 工程包含相同的十层楼宇与单台电梯，分别播放正常乘梯和防夹重开场景。人物编号和轨迹来自项目仿真核心，动画已烘焙为关键帧。无需启用脚本自动运行，也没有外部贴图依赖。

## 直接打开

在 Blender 4.5 LTS 或兼容的新版本中打开：

- `assets/blender/normal_ride.blend`：两名乘客在首层上梯，分别到达 4 层与 8 层；仿真约 41 秒。
- `assets/blender/anti_pinch.blend`：第二人在第 8 秒到达正在关闭的门前，仿真触发一次重开；两人随后分别到达目标层，仿真约 40 秒。

本机便携版在 `E:\GitHub\Multifunctional-Elevator\.tools\blender-4.5.9-windows-x64\blender.exe`。可双击 `scripts/打开正常乘梯.cmd` 或 `scripts/打开防夹演示.cmd`。

右上角 Scene 下拉菜单有三个场景：

| Scene 名称后缀 | 内容 |
|---|---|
| Hall | 一层完整大厅，包括石材、金属门、木饰面、照明、人物和检测提示 |
| Section | 十层建筑剖面，隐藏门面与吊顶以暴露井道，保留移动轿厢、导轨和简化配重 |
| Cabin | 随轿厢移动的内部观察镜头 |

空格播放；数字小键盘 0 进入相机视图；拖动时间线可查看指定时刻。帧率为 24 FPS，第 1 帧对应仿真第 0 秒；第 `1 + 秒数 × 24` 帧对应该仿真时刻。时间线标记标出开门、乘客进出与防夹重开。

`media/demos/` 是便于观看的 MP4 预览，使用 GPU Cycles 低采样加降噪渲染：正常片段交替使用大厅和剖面视角；防夹关键动作放慢到 0.8 倍，运行片段加快到 3 倍。完整原始时序仍保存在 `.blend` 与 JSON 中，具体剪辑速度见视频旁的 `*_shots.json`。

## 场景与材质编辑

Collection 按结构、门面、动画、灯光、相机和剖面标签分组。轿厢根对象为 `E01 | car root`，人物根对象为 `Passenger_001`、`Passenger_002`，各人物带 `passenger_id` 属性。Hall、Section、Cabin 共用资产与动画，修改物件会同步反映到其他视角。

场景单位为米，楼层高 3.5 米是展示参数。门板独立动画，轿厢、厅门与轿门均可编辑；材质使用 Principled BSDF，石材细节为程序纹理。所有模型均由本项目脚本生成，人物采用简化造型，适合后续替换为带许可的高精度人物。

默认使用 Cycles、48 采样与降噪。快速调整可切换 Eevee；不同引擎的反射和光照表现会有差异。推荐最终视频先渲染 PNG 序列，再合成为视频，便于中断后继续。

## 从源码重建

仿真运行依赖原有 Python 环境，建模脚本由 Blender 内置 Python 运行，不需要把 `bpy` 安装到项目虚拟环境。

重建需要 Blender 4.5 LTS 和 Python 3.10 以上；生成视频需要 PATH 中可用的 FFmpeg，交付检查还需要 FFprobe。仅打开和播放 `.blend` 工程无需项目虚拟环境或 FFmpeg。

```powershell
# 本机已配置的环境
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/export_demo_replays.py

# 重建两个工程并核对烘焙后的物件位置
.\scripts\build_blender.ps1

# 工程已存在时，只验证与渲染
.\scripts\build_blender.ps1 -VerifyOnly -Stills -Previews

# 使用另一处安装的 Blender
.\scripts\build_blender.ps1 -BlenderPath 'E:\path\to\blender.exe'
```

项目输出、临时文件及 Blender 用户配置均由脚本指定在项目目录下。Blender 程序、缓存、渲染帧与日志不进入 Git；可重建的 MP4、精选 PNG、JSON 轨迹和 `.blend` 工程进入本分支。

## 仿真与展示的对应关系

`scripts/export_demo_replays.py` 使用 `Simulation.step()` 导出真实状态与事件，`blender/build_scene.py` 把轿厢位置、门开度和人员行程烘焙为关键帧。`blender/verify_scene.py` 重新打开保存后的文件，逐个整数时刻检查门板与轿厢位置是否和 JSON 一致。

现有核心是每秒一步，人员进出在统计上是瞬时事件。画面中的走路动作在开门保持期内完成，未新增人群动力学或重新计算通行时间。剖面会主动移除遮挡的门面，这是展示视图。传感器检测区是教学叠层，场景不接真实设备，也不构成传感器或电梯安全验证。
