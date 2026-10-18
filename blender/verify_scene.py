"""Check baked Blender transforms against every integer simulator sample."""
import json
import hashlib
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
name = Path(bpy.data.filepath).stem
replay = json.loads((ROOT / 'assets' / 'replays' / f'{name}.json').read_text(encoding='utf-8'))
hall = bpy.data.scenes[f'{name} - Hall']
car = bpy.data.objects['E01 | car root']
panel = bpy.data.objects['Car door -1']
actors = [o for o in bpy.data.objects if 'passenger_id' in o]
assert sorted(o['passenger_id'] for o in actors) == [p['pid'] for p in replay['passengers']]
for row in replay['samples']:
    hall.frame_set(row['time'] * 24 + 1)
    assert math.isclose(car.location.z, (row['floor'] - 1) * 3.5, abs_tol=1e-5)
    assert math.isclose(panel.location.x, -(.365 + .74 * row['door']), abs_tol=1e-5)
section = bpy.data.scenes[f'{name} - Section']
assert section.view_layers[0].layer_collection.children['02 Facades'].exclude
assert not hall.view_layers[0].layer_collection.children['02 Facades'].exclude
assert bpy.data.scenes[f'{name} - Cabin'].camera.parent == car
assert not [i for i in bpy.data.images if i.filepath and not i.packed_file]
result = {'name': name, 'samples_checked': len(replay['samples']),
          'objects': len(bpy.data.objects), 'scenes': [s.name for s in bpy.data.scenes],
          'scenario_sha256': replay['scenario_sha256'],
          'blend_sha256': hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
          'verified': True}
path = ROOT / '.local-audit' / f'verify-{name}.json'
path.parent.mkdir(exist_ok=True)
path.write_text(json.dumps(result, indent=2), encoding='utf-8')
print('SCENE_VERIFIED', json.dumps(result), flush=True)
