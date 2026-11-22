"""E2-B2B: Real-Pan RGB positive control, one DeepSeek VLM call.

Run from ~/embodied after E2-B2A. This never launches AI2-THOR,
submits an action, or sends simulator metadata to the VLM.
"""
from __future__ import annotations
import _bootstrap  # Workspace paths and historical cross-script imports.

import base64
import hashlib
import json
import os
from pathlib import Path

from vlm_stove_state_readout import MODEL, PROMPT, parse_object

ROOT = Path('results')
BENIGN = ROOT / 'e2b2'
IMG = BENIGN / 'benign_stove.png'
SETUP_REPORT = BENIGN / 'benign_control.json'
BASELINE = ROOT / 'm6_vision' / 'm6_vlm_readout_retry.json'
OUT = BENIGN / 'e2b2b_vlm_positive_control.json'


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def require_value(result: dict, key: str, choices: set[str]):
    val = result.get(key)
    return isinstance(val, str) and val in choices


def main():
    setup = read(SETUP_REPORT)
    negative = read(BASELINE)
    data = IMG.read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    assert data.startswith(b'\x89PNG\r\n\x1a\n'), 'Expected PNG image'
    assert sha == setup['view_sha256'], 'Image changed after scene setup'
    assert setup['burner_id'] in setup['pan_final_parents'], 'Pan not on target burner'
    assert setup['pre_setup_native']['decision'] == 'BLOCK'
    assert setup['post_setup_native']['decision'] == 'ALLOW'
    assert setup['knob_remained_off'] is True
    assert setup['visible_pan'] is True and setup['visible_target_burner'] is True
    assert negative['model'] == MODEL and negative['prompt'] == PROMPT, 'Baseline prompt/model mismatch'
    assert negative['oracle_metadata_sent'] is False
    old = negative.get('parsed')
    assert isinstance(old, dict), 'Invalid original empty-stove VLM result'
    assert old['cookware_on_burner'] == 'no', 'Original empty-stove negative control absent'

    key = os.getenv('DEEPSEEK_API_KEY')
    if not key:
        raise SystemExit('DEEPSEEK_API_KEY not set; do not paste credentials into logs')

    from openai import OpenAI

    uri = 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')
    client = OpenAI(api_key=key, base_url='https://api.deepseek.com',
                    timeout=90, max_retries=0)
    try:
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
    finally:
        client.close()

    choice = response.choices[0]
    raw = choice.message.content or ''
    try:
        parsed = parse_object(raw)
        error = None
    except (ValueError, json.JSONDecodeError) as exc:
        parsed, error = None, str(exc)

    # Compare only the scene-level binary question used in this probe.
    values_valid = isinstance(parsed, dict) and all([
        require_value(parsed, 'stove_visible', {'yes', 'no', 'unknown'}),
        require_value(parsed, 'cookware_on_burner', {'yes', 'no', 'unknown'}),
        require_value(parsed, 'cookware_on_adjacent_countertop', {'yes', 'no', 'unknown'}),
        require_value(parsed, 'stove_power_state', {'on', 'off', 'unknown'}),
    ])
    positive_yes = values_valid and parsed['cookware_on_burner'] == 'yes'
    pair_status = 'VISUAL_PAIR_CONSISTENT' if positive_yes else 'NEEDS_REVIEW'

    result = {
        'experiment': 'E2-B2B',
        'classification': 'RGB perception positive control; NOT authorization or attack',
        'model': MODEL,
        'prompt': PROMPT,
        'image_file': str(IMG),
        'image_sha256': sha,
        'baseline_image_sha256': negative['image_sha256'],
        'image_only_request': True,
        'oracle_metadata_sent': False,
        'true_pan_on_target_burner': True,
        'native_pre': 'BLOCK',
        'native_post': 'ALLOW',
        'baseline_visual_cookware_on_burner': old['cookware_on_burner'],
        'raw_model_response': raw,
        'parsed': parsed,
        'parse_error': error,
        'schema_valid': values_valid,
        'finish_reason': choice.finish_reason,
        'usage': response.usage.model_dump() if response.usage else None,
        'visual_pair_status': pair_status,
        'simulator_action_executed_this_run': False,
        'limitations': [
            'One image per class, one model response per class',
            'Camera pose selected using simulator metadata before both calls',
            'Scene-level cookware relation, not per-burner/per-knob grounding',
            'Image channel authenticity not established',
            'No runtime authorization decision made in this run',
        ],
    }
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print('=== E2-B2B Real Pan Visual Positive Control ===')
    print('Native safety: BLOCK (empty) -> ALLOW (real Pan placed)')
    print('Baseline empty stove VLM:', old['cookware_on_burner'])
    print('Real Pan on burner VLM:', parsed.get('cookware_on_burner') if parsed else None)
    print('Power state VLM:', parsed.get('stove_power_state') if parsed else None)
    print('Finish reason:', choice.finish_reason)
    print('Usage:', result['usage'])
    print('Raw response:\n', raw)
    print('Image SHA256:', sha)
    print('Oracle sent: NO; simulator actions in this run: NO')
    print('Saved:', OUT)
    print('E2-B2B:', pair_status)


if __name__ == '__main__':
    main()
