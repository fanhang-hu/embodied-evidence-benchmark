"""E2-B2C: Offline audit of the empty-stove vs real-pan RGB pair.

No simulator, VLM, API key or execution required. Run from ~/embodied.
"""
import _bootstrap  # Workspace paths and historical cross-script imports.
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageEnhance, ImageDraw

ROOT = Path('results')
EMPTY = ROOT / 'm6_vision' / 'stove_view.png'
PAN = ROOT / 'e2b2' / 'benign_stove.png'
SETUP = ROOT / 'e2b2' / 'benign_control.json'
VLM = ROOT / 'e2b2' / 'e2b2b_vlm_positive_control.json'
BASELINE = ROOT / 'm6_vision' / 'm6_vlm_readout_retry.json'
OUT = ROOT / 'e2b2'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    setup, vlm, baseline = read(SETUP), read(VLM), read(BASELINE)
    empty_sha, pan_sha = sha(EMPTY), sha(PAN)
    assert empty_sha == baseline['image_sha256'], 'Empty image hash does not match VLM input'
    assert pan_sha == setup['view_sha256'] == vlm['image_sha256'], 'Pan image hash mismatch'
    assert empty_sha != pan_sha, 'Both images are byte-identical: inspect capture pipeline'
    assert setup['burner_id'] in setup['pan_final_parents'], 'Positive scene is not physically on burner'
    assert setup['post_setup_native']['decision'] == 'ALLOW', 'Positive native safety not ALLOW'

    with Image.open(EMPTY) as f:
        empty = f.convert('RGB')
    with Image.open(PAN) as f:
        pan = f.convert('RGB')
    assert empty.size == pan.size, f'Different image sizes: {empty.size} vs {pan.size}'

    a = np.asarray(empty).astype(np.int16)
    b = np.asarray(pan).astype(np.int16)
    diff = np.abs(a - b)
    max_ch = diff.max(axis=2)
    mask = max_ch >= 30
    ys, xs = np.where(mask)
    bbox = None if len(xs) == 0 else [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    pct = float(mask.mean() * 100)
    avg = float(diff.mean())
    peak = int(diff.max())

    # Diff visualization: highlights where the images differ, not a trusted object mask.
    diff_img = ImageEnhance.Contrast(ImageChops.difference(empty, pan)).enhance(3)
    diff_img = ImageEnhance.Brightness(diff_img).enhance(2)
    scale = 3
    w, h = empty.size
    board = Image.new('RGB', (w * scale * 3, h * scale + 44), 'white')
    draw = ImageDraw.Draw(board)
    for k, (title, img) in enumerate([
        ('EMPTY stove | M6-3C', empty),
        ('REAL PAN on burner | E2-B2A', pan),
        ('ABS pixel difference x6 | diagnostic only', diff_img),
    ]):
        x = k * w * scale
        draw.text((x + 10, 13), title, fill='black')
        board.paste(img.resize((w * scale, h * scale), Image.Resampling.NEAREST), (x, 44))

    out_image = OUT / 'e2b2c_empty_vs_pan_vs_diff.png'
    board.save(out_image)
    report = {
        'experiment': 'E2-B2C',
        'empty_image_sha256_verified': empty_sha,
        'positive_image_sha256_verified': pan_sha,
        'pixel_difference': {
            'mean_absolute_channel_difference': avg,
            'maximum_absolute_channel_difference': peak,
            'percent_pixels_with_any_channel_delta_ge_30': pct,
            'bounding_box_of_changed_pixels_xyxy': bbox,
            'warning': 'Difference may also include camera, lighting, or simulation rendering shifts; it is not a Pan segmentation mask.'
        },
        'native_pre': setup['pre_setup_native']['decision'],
        'native_post': setup['post_setup_native']['decision'],
        'original_pan_ground_truth_parent': setup['pan_final_parents'],
        'empty_vlm_answer': baseline.get('parsed'),
        'positive_vlm_answer': vlm.get('parsed'),
        'further_vlm_calls': 0,
        'simulator_actions': 0,
        'visual_comparison': str(out_image),
    }
    report_path = OUT / 'e2b2c_visual_pair_audit.json'
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('=== E2-B2C Visual Pair Audit ===')
    print('Both images match VLM-input SHA256: YES')
    print('The two image bytes differ: YES')
    print('Mean absolute pixel-channel delta: %.3f' % avg)
    print('Pixels changed >=30 in any channel: %.2f%%' % pct)
    print('Changed region bounding box (xyxy):', bbox)
    print('Actual pan parent includes target burner: YES')
    print('Native before -> after:', setup['pre_setup_native']['decision'], '->', setup['post_setup_native']['decision'])
    print('Empty VLM cookware_on_burner:', (baseline.get('parsed') or {}).get('cookware_on_burner'))
    print('Real-pan VLM cookware_on_burner:', (vlm.get('parsed') or {}).get('cookware_on_burner'))
    print('Saved comparison:', out_image)
    print('Saved report:', report_path)
    print('E2-B2C AUDIT COMPLETE; MANUAL IMAGE REVIEW REQUIRED')


if __name__ == '__main__':
    main()
