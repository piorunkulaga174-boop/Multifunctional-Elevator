"""Verify shipped video decoding, scene receipts and paired input provenance."""
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    result = {}
    for name, count in (('normal_ride', 202), ('anti_pinch', 226)):
        blend = ROOT / 'assets' / 'blender' / f'{name}.blend'
        receipt = json.loads((ROOT / '.local-audit' / f'verify-{name}.json').read_text())
        assert receipt['verified'] and len(receipt['scenes']) == 3
        assert receipt['blend_sha256'] == hashlib.sha256(blend.read_bytes()).hexdigest()
        movie = ROOT / 'media' / 'demos' / f'{name}.mp4'
        probe = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
            'stream=width,height,nb_frames,r_frame_rate', '-show_entries', 'format=duration',
            '-of', 'json', str(movie)]))
        video = probe['streams'][0]
        assert int(video['nb_frames']) == count
        assert (video['width'], video['height']) == (768, 432)
        shots = json.loads((ROOT / 'media' / 'demos' / f'{name}_shots.json').read_text())
        assert len(shots) == count
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(movie), '-f', 'null', '-'], check=True)
        result[name] = {'frames': count, 'seconds': float(probe['format']['duration']),
                        'scenes_verified': 3, 'samples_verified': receipt['samples_checked'],
                        'blend_sha256': receipt['blend_sha256'],
                        'movie_sha256': hashlib.sha256(movie.read_bytes()).hexdigest()}
    with (ROOT / 'experiments' / 'paired_v1' / 'experiment_detail.csv').open(encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    for seed in range(42, 52):
        paired = [r for r in rows if int(r['种子']) == seed]
        assert len(paired) == 3
        assert len({r['输入场景SHA256'] for r in paired}) == 1
        assert len({r['总乘客数'] for r in paired}) == 1
    assert Image.open(ROOT / 'assets' / 'previews' / 'full_section.png').size == (900, 1280)
    for name in ('normal_hall', 'anti_pinch', 'cabin'):
        assert Image.open(ROOT / 'assets' / 'previews' / f'{name}.png').size == (1280, 720)
    result['paired_runs_verified'] = len(rows)
    out = ROOT / '.local-audit' / 'deliverables-verified.json'
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
