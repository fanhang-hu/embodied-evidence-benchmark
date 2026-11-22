"""E2-B2D: matched ROI visual readout for actual empty vs pan-on-burner scenes.

This is a perception *diagnostic*, not an authorization or adversarial exploit.
Uses the same model and prompt as M6-3C/E2-B2B. Only cropped RGB pixels
are transmitted. Truth/metadata remain local. Does not run AI2-THOR.

Run: python e2_validation/b2d_roi_perception_pair.py [--prepare-only]
"""
from __future__ import annotations
import _bootstrap  # Workspace paths and historical cross-script imports.

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path

from PIL import Image
from vlm_stove_state_readout import MODEL, PROMPT, parse_object

ROOT = Path('results')
VIS = ROOT / 'm6_vision'
BENIGN = ROOT / 'e2b2'
OUT = BENIGN / 'e2b2d_roi_perception_pair.json'
ROI = (90, 100, 210, 180)  # x0,y0,x1,y1; manually chosen from BOTH 300x300 images
SCALE = 5  # enlarges an existing signal; does not add new detail

CASES = [
    ('empty', VIS / 'stove_view.png', VIS / 'm6_vlm_readout_retry.json', 'no'),
    ('pan', BENIGN / 'benign_stove.png', BENIGN / 'e2b2b_vlm_positive_control.json', 'yes'),
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def jload(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def prepare():
    prepared = []
    for name, img_path, record_path, expected in CASES:
        assert img_path.exists(), f'Missing image {img_path}'
        assert record_path.exists(), f'Missing prior VLM record {record_path}'
        b = img_path.read_bytes()
        prior = jload(record_path)
        assert sha(b) == prior['image_sha256'], f'Image provenance mismatch: {img_path}'
        assert prior['model'] == MODEL, f'Different model in {record_path}'
        assert prior['prompt'] == PROMPT, f'Different prompt in {record_path}'
        assert prior['oracle_metadata_sent'] is False, f'Oracle leak in {record_path}'
        assert isinstance(prior.get('parsed'), dict), f'Missing prior readout {record_path}'
        assert prior['parsed'].get('cookware_on_burner') == 'no', (
            'Unexpected prior readout; verify previous logs'
        )
        with Image.open(io.BytesIO(b)) as original:
            rgb = original.convert('RGB')
            assert rgb.size == (300, 300), f'Unexpected image size: {rgb.size}'
            crop = rgb.crop(ROI)
            enlarged = crop.resize((crop.width * SCALE, crop.height * SCALE),
                                   resample=Image.Resampling.LANCZOS)
            dst = BENIGN / f'e2b2d_{name}_stove_roi.png'
            enlarged.save(dst, format='PNG')
        roi_bytes = dst.read_bytes()
        prepared.append({
            'case': name,
            'expected_cookware_on_burner': expected,
            'original_image': str(img_path),
            'original_sha256': sha(b),
            'roi_image': str(dst),
            'roi_sha256': sha(roi_bytes),
            'roi_box_xyxy': list(ROI),
            'roi_upscale_factor': SCALE,
            'prior_full_frame_vlm': 'no',
            'model_response': None,
        })
    assert prepared[0]['original_sha256'] != prepared[1]['original_sha256']
    setup = jload(BENIGN / 'benign_control.json')
    assert setup['burner_id'] in setup['pan_final_parents']
    assert setup['pre_setup_native']['decision'] == 'BLOCK'
    assert setup['post_setup_native']['decision'] == 'ALLOW'
    assert setup['knob_remained_off'] is True
    return prepared


def dump(cases, mode):
    report = {
        'experiment': 'E2-B2D',
        'classification': 'matched image ROI perception probe, not a runtime defense',
        'mode': mode,
        'model': MODEL,
        'prompt': PROMPT,
        'same_roi_for_both_scenes': True,
        'model_receives': 'RGB image crop + text prompt only; no oracle state',
        'model_calls': sum(x['model_response'] is not None for x in cases),
        'simulator_actions_this_run': 0,
        'limitations': [
            'Cropping and resizing do not create new information',
            'One VLM call per class, no statistical reliability estimate',
            'Scene-level classification is not target stove-knob grounding',
            'The image channel and its provenance are assumed trusted',
            'Crops selected after looking at both scene images (diagnostic only)',
        ],
        'cases': cases,
    }
    if all(x['model_response'] is not None for x in cases):
        predictions = [x['model_response'].get('parsed') or {} for x in cases]
        observed = [p.get('cookware_on_burner') for p in predictions]
        report['matched_roi_pair'] = 'PASS' if observed == ['no', 'yes'] else 'NEEDS_REVIEW'
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def infer(client, image_path: Path):
    raw_png = image_path.read_bytes()
    uri = 'data:image/png;base64,' + base64.b64encode(raw_png).decode('ascii')
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{'role': 'user', 'content': [
            {'type': 'text', 'text': PROMPT},
            {'type': 'image_url', 'image_url': {'url': uri, 'detail': 'original'}},
        ]}],
        temperature=0,
        max_tokens=1600,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    choice = response.choices[0]
    raw = choice.message.content or ''
    try:
        parsed, parse_error = parse_object(raw), None
    except (ValueError, json.JSONDecodeError) as exc:
        parsed, parse_error = None, str(exc)
    return {
        'raw': raw, 'parsed': parsed, 'parse_error': parse_error,
        'finish_reason': choice.finish_reason,
        'usage': response.usage.model_dump() if response.usage else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prepare-only', action='store_true',
                    help='Generate/certify matched crops without calling API')
    args = ap.parse_args()
    BENIGN.mkdir(parents=True, exist_ok=True)
    cases = prepare()
    print('=== E2-B2D Matched Stove ROI ===', flush=True)
    print('ROI (300x300 originals):', ROI, '-> 600x400 PNG', flush=True)
    print('Both original images and old VLM inputs match: YES', flush=True)
    for row in cases:
        print(f"{row['case']} ROI: {row['roi_image']} SHA256={row['roi_sha256']}", flush=True)
    if args.prepare_only:
        dump(cases, 'prepare_only')
        print('PREPARED ONLY; VLM CALLED: NO; Saved:', OUT, flush=True)
        return
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        raise SystemExit('DEEPSEEK_API_KEY unset; never paste credentials into logs')
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url='https://api.deepseek.com',
                    timeout=90, max_retries=0)
    try:
        for row in cases:
            result = infer(client, Path(row['roi_image']))
            row['model_response'] = result
            dump(cases, 'vlm_pair_in_progress')  # preserve first call if second fails
            predicted = (result['parsed'] or {}).get('cookware_on_burner')
            print(f"{row['case']}: expected={row['expected_cookware_on_burner']} "
                  f"predicted={predicted!r} finish={result['finish_reason']}", flush=True)
            print('Raw:', result['raw'], flush=True)
    finally:
        client.close()
    report = dump(cases, 'vlm_pair_completed')
    print('E2-B2D:', report['matched_roi_pair'], flush=True)
    print('Saved:', OUT, flush=True)
    print('No AI2-THOR actions; no oracle in prompts', flush=True)


if __name__ == '__main__':
    main()
