"""Build editable architectural scenes and bake simulator replays into Blender.

blender --background --factory-startup --python blender/build_scene.py -- --name normal_ride
Only Blender's bundled bpy and Python standard library are required.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
FPS = 24
FLOOR_H = 3.5
CURRENT_COLLECTION = None


def collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def put(obj, name, material=None, parent=None):
    obj.name = name
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    CURRENT_COLLECTION.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    if parent:
        obj.parent = parent
    return obj


def material(name, color, metal=0, rough=0.4, emission=0, transmission=0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Transmission Weight"].default_value = transmission
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
        bsdf.inputs["Emission Strength"].default_value = emission
    return m


def stone_material():
    m = material("Limestone | fine honed mineral", (.43, .39, .32), rough=.38)
    nodes, links = m.node_tree.nodes, m.node_tree.links
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 85
    noise.inputs["Detail"].default_value = 2
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .12
    bump.inputs["Distance"].default_value = .015
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], nodes.get("Principled BSDF").inputs["Normal"])
    return m


def empty(name, loc=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    CURRENT_COLLECTION.objects.link(obj)
    obj.location = loc
    if parent:
        obj.parent = parent
    return obj


def box(name, loc, dims, mat, bevel=.025, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = put(bpy.context.object, name, mat, parent)
    obj.scale = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Machined edge", "BEVEL")
        mod.width, mod.segments = bevel, 3
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj


def sphere(name, loc, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=loc)
    obj = put(bpy.context.object, name, mat, parent)
    obj.scale = scale
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def rod(name, a, b, radius, mat, parent=None):
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=radius, depth=(b - a).length,
                                      location=(a + b) / 2)
    obj = put(bpy.context.object, name, mat, parent)
    obj.rotation_euler = (b - a).to_track_quat('Z', 'Y').to_euler()
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def text(name, body, loc, size, mat, parent=None, align="CENTER"):
    data = bpy.data.curves.new(name, "FONT")
    data.body, data.size, data.align_x = body, size, align
    data.extrude, data.bevel_depth = .0008, .0004
    obj = bpy.data.objects.new(name, data)
    CURRENT_COLLECTION.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (math.pi / 2, 0, 0)
    obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def area(name, loc, energy, size, color=(1, .86, .7), target=None):
    light = bpy.data.lights.new(name, "AREA")
    light.energy, light.shape, light.size, light.color = energy, "DISK", size, color
    obj = bpy.data.objects.new(name, light)
    CURRENT_COLLECTION.objects.link(obj)
    obj.location = loc
    if target is not None:
        obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    return obj


def camera(name, loc, target, lens=42, ortho=None, parent=None):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name, data)
    CURRENT_COLLECTION.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    data.lens, data.clip_end = lens, 500
    if ortho:
        data.type, data.ortho_scale = "ORTHO", ortho
    if parent:
        obj.parent = parent
    return obj


def human(pid, color, skin, x):
    root = empty(f"Passenger_{pid:03d}")
    root["passenger_id"] = pid
    jacket = material(f"P{pid} | woven jacket", color, rough=.75)
    skin = material(f"P{pid} | skin", skin, rough=.55)
    trousers = material(f"P{pid} | charcoal trousers", (.027, .034, .044), rough=.8)
    shoes = material(f"P{pid} | leather", (.015, .018, .022), rough=.33)
    shirt = material(f"P{pid} | shirt", (.72, .77, .75), rough=.85)
    hair = material(f"P{pid} | hair", (.025, .017, .012), rough=.7)
    # Rounded, editable demonstration characters with human proportions.
    sphere("Pelvis", (0, 0, .91), (.17, .12, .14), trousers, root)
    sphere("Tailored jacket", (0, 0, 1.21), (.23, .13, .30), jacket, root)
    box("Shirt placket", (0, -.123, 1.34), (.085, .022, .23), shirt, .012, root)
    rod("Neck", (0, 0, 1.44), (0, 0, 1.53), .055, skin, root)
    sphere("Head", (0, -.004, 1.65), (.104, .092, .137), skin, root)
    sphere("Hair cap", (0, .006, 1.742), (.108, .096, .065), hair, root)
    sphere("Nose", (0, -.092, 1.65), (.019, .026, .022), skin, root)
    for side in (-1, 1):
        sphere("Eye", (side * .037, -.084, 1.679), (.009, .006, .006), shoes, root)
        sphere("Ear", (side * .103, 0, 1.65), (.017, .017, .028), skin, root)
    joints = []
    for side in (-1, 1):
        leg = empty(f"P{pid} leg {side}", (side * .092, 0, .91), root)
        rod("Trouser leg", (0, 0, -.04), (0, 0, -.80), .069, trousers, leg)
        sphere("Knee", (0, 0, -.40), (.072, .071, .08), trousers, leg)
        box("Shoe", (0, -.055, -.855), (.135, .25, .10), shoes, .035, leg)
        arm = empty(f"P{pid} arm {side}", (side * .215, 0, 1.40), root)
        rod("Jacket sleeve", (0, 0, 0), (side * .025, .005, -.45), .058, jacket, arm)
        sphere("Hand", (side * .025, 0, -.50), (.045, .04, .068), skin, arm)
        joints.append((leg, arm, side))
    root["queue_x"] = x
    return root, joints


def sample_at(replay, time):
    rows = replay["samples"]
    i = min(max(int(math.floor(time)), 0), len(rows) - 1)
    a, b = rows[i], rows[min(i + 1, len(rows) - 1)]
    k = max(0, min(1, time - i))
    return {"floor": a["floor"] * (1 - k) + b["floor"] * k,
            "door": a["door"] * (1 - k) + b["door"] * k,
            "at_floor": a["at_floor"], "state": a["state"]}


def actor_position(replay, p, time, queue_x):
    call, board, arrive = p["call_time"], p["board_time"], p["arrive_time"]
    origin_z, target_z = (p["origin"] - 1) * FLOOR_H, (p["target"] - 1) * FLOOR_H
    late = replay["name"] == "anti_pinch" and p["pid"] == 2
    if time < call - 2:
        return (queue_x, -4, origin_z), 0, False
    if time < call:
        u = (time - call + 2) / 2
        y = -3.9 + u * (3.75 if late else 2.5)
        return (queue_x + (1 - u) * .9, y, origin_z), 1, True
    if time < board:
        return (queue_x, -.15 if late else -1.4, origin_z), 1, False
    if time < board + 1.8:
        u = (time - board) / 1.8
        y = (-.15 if late else -1.4) * (1 - u) + 1.35 * u
        step_up = .10 * max(0, min(1, y / .3))
        return (queue_x, y, origin_z + step_up), 1, True
    if time < arrive:
        return (queue_x, 1.35, (sample_at(replay, time)["floor"] - 1) * FLOOR_H + .10), 1, False
    if time < arrive + 4:
        u = (time - arrive) / 4
        y = 1.35 - u * 6.2
        return (queue_x, y, target_z + .10 * max(0, min(1, y / .3))), 1, True
    return (queue_x, -5, target_z), 0, False


def build(replay):
    global CURRENT_COLLECTION
    bpy.ops.wm.read_factory_settings(use_empty=True)
    hall = bpy.context.scene
    hall.name = f"{replay['name']} - Hall"
    bpy.context.preferences.edit.keyframe_new_interpolation_type = 'LINEAR'
    structure, facade, dynamics, lighting, cameras, annotations = [collection(n) for n in
        ("01 Structure", "02 Facades", "03 Replay rig", "04 Lighting", "05 Cameras", "06 Section labels")]
    stone = stone_material()
    plaster = material("Warm plaster", (.60, .55, .46), rough=.78)
    dark = material("Graphite steel", (.025, .035, .044), metal=.65, rough=.32)
    bronze = material("Brushed champagne aluminum", (.48, .31, .14), metal=.82, rough=.27)
    stainless = material("Satin stainless", (.40, .46, .48), metal=.86, rough=.23)
    wood = material("Walnut acoustic fins", (.12, .058, .025), rough=.54)
    glass = material("Smoked architectural glass", (.10, .21, .25), rough=.12, transmission=.72)
    warm = material("Warm linear light", (1, .70, .36), emission=3)
    cool = material("Cyan instrument light", (.05, .65, .78), emission=3)
    white = material("Sign lettering", (.78, .87, .88), rough=.3)
    ink = material("Graphite lettering", (.025, .036, .044), rough=.6)
    green = material("Status green", (.05, .64, .29), emission=2)
    amber = material("Door protection amber", (1, .28, .025), emission=3)
    grout = material("Stone grout", (.16, .145, .12), rough=.75)

    CURRENT_COLLECTION = structure
    box("Exhibition plinth", (0, -.4, -.36), (8.2, 8.3, .55), dark, .12)
    box("Ground", (0, 0, -.72), (200, 200, .12), material("Backdrop", (.035, .045, .060), rough=.8), 0)
    for level in range(10):
        z = level * FLOOR_H
        # Shaft void stays open: no slab intersects the moving car.
        box(f"L{level+1:02d} lobby slab", (0, -2.1, z - .11), (7.4, 4.4, .22), stone, .035)
        for side in (-1, 1):
            box("Side slab", (side * 2.65, 1.45, z - .11), (2.1, 2.9, .22), stone, .035)
            box("Section rear wing wall", (side * 2.65, 2.85, z + 1.57), (2.1, .13, 3.14), plaster, .018)
            box("Section rear window", (side * 2.65, 2.77, z + 1.75), (1.48, .035, 1.70), glass, .012)
            box("Section window sill", (side * 2.65, 2.68, z + .90), (1.60, .24, .065), bronze, .012)
            box("Perimeter column", (side * 3.55, 2.75, z + 1.64), (.20, .22, 3.28), dark, .015)
            box("Shaft rail", (side * 1.44, 2.5, z + 1.7), (.065, .085, 3.5), stainless, .006)
            box("Section edge light", (side * 3.63, -4.12, z + .03), (.035, .12, .04), cool, .005)
        # Fine grout gives a sense of scale without hundreds of separate tiles.
        for x in range(-3, 4):
            box("Stone joint", (x, -2.1, z + .006), (.005, 4.3, .005), grout, 0)
        for y in (-3.4, -2.4, -1.4, -.4):
            box("Stone joint", (0, y, z + .006), (7.2, .005, .005), grout, 0)
        box("Back shaft beam", (0, 2.85, z + 2.95), (3.0, .18, .18), dark, .015)
        # Low transparent balustrades make the exposed architectural section legible.
        for side in (-1, 1):
            box("Guard rail glazing", (side * 2.65, -4.16, z + .50), (1.9, .025, .9), glass, .006)
            rod("Guard rail cap", (side * 1.7, -4.16, z + .98),
                (side * 3.6, -4.16, z + .98), .018, bronze)

    CURRENT_COLLECTION = facade
    hall_doors = []
    for level in range(10):
        z = level * FLOOR_H
        for side in (-1, 1):
            box("Limestone wall", (side * 2.23, .04, z + 1.62), (2.70, .18, 3.24), plaster, .018)
            box("Bronze jamb", (side * .82, -.06, z + 1.18), (.11, .16, 2.4), bronze, .015)
            panel = box(f"Hall door L{level+1:02d} {side}",
                        (side * .365, .012, z + 1.175), (.726, .055, 2.35), stainless, .012)
            hall_doors.append((panel, side, level + 1))
        box("Door lintel", (0, -.04, z + 2.43), (1.76, .20, .18), bronze, .018)
        box("Header wall", (0, .04, z + 2.87), (1.70, .18, .70), plaster, .015)
        box("Door header glass", (0, -.15, z + 2.69), (.76, .055, .26), dark, .015)
        text("Floor designation", f"L {level+1:02d}", (0, -.186, z + 2.64), .13, white)
        box("Sill", (0, .0, z + .02), (1.60, .24, .035), stainless, .008)
        for i in range(13):
            box("Acoustic wall fin", (-3.36 + i * .115, -.09, z + 1.56), (.043, .10, 2.98), wood, .008)
        text("Wayfinding", f"{level+1:02d}", (2.13, -.074, z + 1.57), .48, ink)
        text("Wayfinding subtitle", "VERTICAL TRANSIT", (2.13, -.078, z + 1.29), .074, ink)
        box("Call panel", (1.03, -.13, z + 1.19), (.15, .07, .37), dark, .022)
        for dz, label in ((.08, "+"), (-.08, "-")):
            text("Call button", label, (1.03, -.174, z + 1.19 + dz), .09, warm)
        box("Presence sensor", (1.0, -.12, z + 2.51), (.10, .07, .08), dark, .022)
        sphere("Sensor status", (1.0, -.17, z + 2.51), (.014, .007, .014), green)
        box("Acoustic ceiling", (0, -1.9, z + 3.27), (7.3, 4.3, .10), plaster, .025)
        for x in (-2.0, 0, 2.0):
            box("Ceiling light", (x, -1.8, z + 3.204), (.045, 2.6, .022), warm, .008)
    text("Lobby sign", "ELEVATOR 01", (-2.7, -.17, 2.35), .10, white)

    CURRENT_COLLECTION = dynamics
    car = empty("E01 | car root")
    box("Car floor", (0, 1.40, .04), (2.48, 2.65, .11), stone, .035, car)
    box("Car rear wall", (0, 2.69, 1.38), (2.5, .08, 2.7), wood, .02, car)
    for side in (-1, 1):
        box("Car side wall", (side * 1.24, 1.4, 1.38), (.07, 2.65, 2.70), bronze, .02, car)
        rod("Car handrail", (side * 1.16, .6, 1.0), (side * 1.16, 2.3, 1.0), .022, stainless, car)
        box("Car rear light", (side * 1.09, 2.63, 1.38), (.025, .02, 2.5), warm, .003, car)
    box("Car ceiling", (0, 1.4, 2.73), (2.5, 2.65, .10), dark, .03, car)
    box("Car ceiling diffuser", (0, 1.4, 2.66), (1.8, 1.8, .025), warm, .02, car)
    box("Car control panel", (1.185, .85, 1.27), (.035, .30, .61), dark, .015, car)
    car_doors = []
    for side in (-1, 1):
        car_doors.append((box(f"Car door {side}", (side * .365, .16, 1.175),
                              (.726, .048, 2.35), stainless, .012, car), side))
    text("Car ID", "E01", (0, -.01, 2.46), .105, white, car)
    counterweight = empty("Counterweight")
    box("Counterweight mass", (1.6, 2.1, 1.3), (.24, 1.0, 2.2), dark, .04, counterweight)
    # Door-zone lines are an educational overlay, visible in the safety scene only.
    zone_root = empty("Safety overlay | demonstration only")
    for y in (-.4, .35):
        box("Door zone limit", (0, y, .03), (1.55, .018, .014), amber, .003, zone_root)
    for side in (-1, 1):
        box("Door zone side", (side * .775, -.025, .03), (.018, .75, .014), amber, .003, zone_root)
    warning = text("Protection message", "DOOR PROTECTION / REOPEN", (0, -.23, 2.96), .10, amber)
    actors = []
    for i, p in enumerate(replay["passengers"]):
        queue_x = 0 if replay["name"] == "anti_pinch" and p["pid"] == 2 else -.30 + i * .60
        actor, joints = human(p["pid"], ((.045, .095, .15), (.34, .19, .065))[i % 2],
                              ((.55, .32, .20), (.67, .43, .29))[i % 2], queue_x)
        actors.append((p, actor, joints))

    CURRENT_COLLECTION = annotations
    for level in range(10):
        text("Section floor", f"{level+1:02d}", (-4.4, -4.6, level * FLOOR_H + .4), .65, white)
    text("Section title", "VERTICAL TRANSIT", (0, -1.4, 35.3), .45, white)
    text("Section subtitle", "E01  /  10 LEVELS  /  1000 KG", (0, -1.4, 34.65), .18, cool)

    CURRENT_COLLECTION = lighting
    for level in range(10):
        area("Lobby ceiling illumination", (0, -1.7, level * FLOOR_H + 3.12), 230 if level == 0 else 100, 3.2)
    car_light = area("Car cabin illumination", (0, 1.3, 2.59), 70, 1.5)
    car_light.parent = car
    area("Architectural key", (9, -15, 25), 6500, 12, (0.75, .86, 1), (0, 0, 14))
    area("Architectural rim", (-10, 5, 30), 8000, 10, (1, .74, .42), (0, 0, 17))
    area("Lobby fill", (1, -6.0, 2.7), 180, 4, (0.76, .86, 1), (0, .5, 1.1))

    CURRENT_COLLECTION = cameras
    hall_camera = camera("CAM | Hall 01", (4.4, -7.8, 2.5), (0, .20, 1.43), lens=38)
    section_camera = camera("CAM | Ten-floor section", (24, -37, 23), (0, -.4, 16.5), ortho=74)
    cabin_camera = camera("CAM | Cabin (follows car)", (.85, 2.40, 1.75), (-.15, -.6, 1.20), lens=23, parent=car)
    hall.camera = hall_camera
    world = bpy.data.worlds.new("Blue hour studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (.12, .17, .24, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = .35
    hall.world = world

    # All motion is baked. Opening a blend does not require trusting an auto-run script.
    last_time = replay["samples"][-1]["time"]
    for row in replay["samples"]:
        t, frame = row["time"], row["time"] * FPS + 1
        car.location.z = (row["floor"] - 1) * FLOOR_H
        car.keyframe_insert("location", frame=frame)
        counterweight.location.z = (10 - row["floor"]) * FLOOR_H
        counterweight.keyframe_insert("location", frame=frame)
        for panel, side, floor in hall_doors:
            opened = row["door"] if row["at_floor"] == floor else 0
            panel.location.x = side * (.365 + .74 * opened)
            panel.keyframe_insert("location", frame=frame)
        for panel, side in car_doors:
            panel.location.x = side * (.365 + .74 * row["door"])
            panel.keyframe_insert("location", frame=frame)
        active = replay["name"] == "anti_pinch" and 7 <= t <= 11
        zone_root.scale = (1, 1, 1) if active else (0, 0, 0)
        zone_root.keyframe_insert("scale", frame=frame)
        warning.scale = (1, 1, 1) if active and t >= 8 else (0, 0, 0)
        warning.keyframe_insert("scale", frame=frame)
    for quarter in range(int(last_time * 4) + 1):
        t, frame = quarter / 4, quarter * FPS / 4 + 1
        for p, actor, joints in actors:
            loc, visible, walking = actor_position(replay, p, t, actor["queue_x"])
            actor.location, actor.scale = loc, (visible,) * 3
            actor.rotation_euler.z = 0 if t >= p["arrive_time"] else math.pi
            actor.keyframe_insert("location", frame=frame)
            actor.keyframe_insert("scale", frame=frame)
            actor.keyframe_insert("rotation_euler", frame=frame)
            for leg, arm, side in joints:
                swing = math.sin(t * 2 * math.pi * 1.6) * .30 * side if walking else 0
                leg.rotation_euler.x, arm.rotation_euler.x = swing, -swing * .7
                leg.keyframe_insert("rotation_euler", frame=frame)
                arm.keyframe_insert("rotation_euler", frame=frame)

    for ev in replay["events"]:
        marker = hall.timeline_markers.new(f"{ev['type']} {ev.get('pid', '')}")
        marker.frame = ev["time"] * FPS + 1
    hall.frame_start, hall.frame_end = 1, last_time * FPS + 1
    hall.render.fps = FPS
    hall.render.resolution_x, hall.render.resolution_y = 1280, 720
    hall.render.resolution_percentage = 100
    hall.render.engine = "CYCLES"
    hall.cycles.samples = 48
    hall.cycles.use_denoising = True
    hall.render.image_settings.file_format = "PNG"
    hall.view_settings.view_transform = "AgX"
    hall.unit_settings.system = 'METRIC'
    hall.unit_settings.scale_length = 1
    hall["replay_sha256"] = replay["scenario_sha256"]
    hall["source_replay"] = f"//../replays/{replay['name']}.json"
    hall["seconds_per_tick"] = 1
    hall["presentation_note"] = replay["presentation_note"]
    hall.view_layers[0].layer_collection.children[annotations.name].exclude = True

    section = hall.copy()
    section.use_fake_user = True
    section.name = f"{replay['name']} - Section"
    section.camera = section_camera
    section.view_layers[0].layer_collection.children[facade.name].exclude = True
    section.view_layers[0].layer_collection.children[annotations.name].exclude = False
    cabin = hall.copy()
    cabin.use_fake_user = True
    cabin.name = f"{replay['name']} - Cabin"
    cabin.camera = cabin_camera

    guide = bpy.data.texts.new("START HERE - 使用说明")
    guide.write("多功能电梯 Blender 演示\n\n"
                "Scene 下拉菜单：Hall 单层大厅 / Section 十层剖面 / Cabin 随轿厢观察。\n"
                "空格播放，时间线标记对应真实仿真事件；所有动画已烘焙，无需启用脚本自动运行。\n"
                "单位为米，帧率24；人物为原创简化模型，走路动作在开门保持期间进行。\n"
                "剖面场景隐藏厅门墙面以暴露井道；大厅场景保留完整门面。\n"
                "默认使用Cycles，快速预览可选Eevee。\n"
                f"场景：{replay['name']}\n输入 SHA256：{replay['scenario_sha256']}\n")

    # Useful, uncluttered startup view in the standard Blender workspace.
    if bpy.context.window:
        bpy.context.window.scene = hall
    hall.frame_set(4 * FPS + 1)
    for screen in bpy.data.screens:
        for ar in screen.areas:
            if ar.type == 'VIEW_3D':
                ar.spaces.active.region_3d.view_perspective = 'CAMERA'
                ar.spaces.active.shading.type = 'MATERIAL'
    bpy.ops.object.select_all(action='DESELECT')
    return hall, section, cabin


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", choices=("normal_ride", "anti_pinch"), required=True)
    parser.add_argument("--output", type=Path)
    opt = parser.parse_args(args)
    replay = json.loads((ROOT / "assets" / "replays" / f"{opt.name}.json").read_text(encoding="utf-8"))
    scenes = build(replay)
    output = opt.output or ROOT / "assets" / "blender" / f"{opt.name}.blend"
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output))
    print("BUILD_OK", str(output), "objects", len(bpy.data.objects),
          "scenes", [s.name for s in scenes], flush=True)


if __name__ == "__main__":
    main()
