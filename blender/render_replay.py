"""Render stills or short editorial previews from a baked blend."""
import argparse
import json
import sys
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]


def configure(scene, engine, width, height, samples):
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    if scene.camera.data.type == 'ORTHO':
        # Blender fits the scale to the larger image dimension. Keep a 41m
        # vertical field in both landscape and portrait renders.
        scene.camera.data.ortho_scale = 41 * max(width / height, 1)
        for x in (-4.6, 4.6):
            for y in (-4.6, 3.2):
                for z in (-.72, 35.8):
                    uv = world_to_camera_view(scene, scene.camera, Vector((x, y, z)))
                    if not (0 <= uv.x <= 1 and 0 <= uv.y <= 1):
                        raise RuntimeError('Section camera crops the building')
    scene.render.image_settings.file_format = 'PNG'
    scene.render.engine = engine
    if engine == 'CYCLES':
        scene.render.use_persistent_data = True
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        prefs = bpy.context.preferences.addons['cycles'].preferences
        for api in ('OPTIX', 'CUDA'):
            try:
                prefs.compute_device_type = api
                prefs.get_devices()
                gpus = [d for d in prefs.devices if d.type == api]
                if gpus:
                    for d in prefs.devices:
                        d.use = d in gpus
                    scene.cycles.device = 'GPU'
                    print('RENDER_DEVICE', api, [d.name for d in gpus], flush=True)
                    break
            except (TypeError, RuntimeError):
                pass
        else:
            scene.cycles.device = 'CPU'
            print('RENDER_DEVICE CPU', flush=True)
    else:
        scene.eevee.taa_render_samples = samples


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument('--name', required=True)
    p.add_argument('--view', choices=('Hall', 'Section', 'Cabin'), default='Hall')
    p.add_argument('--time', type=float, default=4)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--width', type=int, default=1280)
    p.add_argument('--height', type=int, default=720)
    p.add_argument('--samples', type=int, default=32)
    p.add_argument('--engine', choices=('CYCLES', 'BLENDER_EEVEE_NEXT'), default='CYCLES')
    p.add_argument('--preview', action='store_true')
    opt = p.parse_args(argv)
    if not opt.output.is_absolute():
        opt.output = ROOT / opt.output
    scene = bpy.data.scenes[f'{opt.name} - {opt.view}']
    bpy.context.window.scene = scene
    configure(scene, opt.engine, opt.width, opt.height, opt.samples)
    opt.output.parent.mkdir(parents=True, exist_ok=True)
    if not opt.preview:
        scene.frame_set(round(opt.time * 24) + 1)
        scene.render.filepath = str(opt.output)
        bpy.ops.render.render(write_still=True, scene=scene.name)
        print('STILL_OK', str(opt.output), flush=True)
        return
    # Preview chooses cameras without altering the saved project. Fast travel
    # segments are labelled in the accompanying shot manifest.
    if opt.name == 'normal_ride':
        shots = [('Hall', 0, 9, 1.5), ('Section', 9, 34, 3), ('Section', 34, 39, 2)]
    else:
        shots = [('Hall', 0, 6, 2), ('Hall', 6, 12, .8), ('Section', 12, 37, 3)]
    frames_dir = opt.output
    frames_dir.mkdir(parents=True, exist_ok=True)
    index, manifest = 0, []
    for view, start, end, speed in shots:
        s = bpy.data.scenes[f'{opt.name} - {view}']
        bpy.context.window.scene = s
        configure(s, opt.engine, opt.width, opt.height, opt.samples)
        count = round((end - start) / speed * 12)
        for i in range(count):
            time = start + i / 12 * speed
            frame = time * 24 + 1
            s.frame_set(int(frame), subframe=frame % 1)
            path = frames_dir / f'frame_{index:04d}.png'
            s.render.filepath = str(path)
            bpy.ops.render.render(write_still=True, scene=s.name)
            manifest.append({'index': index, 'time': time, 'view': view, 'speed': speed})
            index += 1
            if index % 12 == 0:
                print('PREVIEW_PROGRESS', opt.name, index, flush=True)
    (frames_dir / 'shots.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('PREVIEW_OK', opt.name, index, flush=True)


if __name__ == '__main__':
    main()
