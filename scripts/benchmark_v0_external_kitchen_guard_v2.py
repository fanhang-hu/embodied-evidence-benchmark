"""Controlled comparison of native and observed-metadata stove target binding.

Only public objects, action, and the requested mapping mode are accepted. The
external safety rules are unchanged; the optional mapping adapter rebuilds the
knob/burner links from public `controlledObjects` with fail-closed validation.
This is a component probe, not the external project's full controller.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'external/safe-hierarchical-embodied-ai/src'))
from ae_rl.execution.kitchen_safety import build_kitchen_snapshot, check_toggle_scene_safety, get_nearby_hazards


def rebind(snapshot):
    burners, knobs = snapshot['burners_by_id'], snapshot['knobs_by_id']
    if not burners or not knobs or len(burners) != len(knobs):
        raise ValueError('Missing or unequal knob/burner sets')
    mapping = {}
    for kid, knob in knobs.items():
        controls = knob.get('controlledObjects')
        if not isinstance(controls, list) or len(controls) != 1 or controls[0] not in burners:
            raise ValueError('Each knob requires one observed burner target')
        mapping[kid] = controls[0]
    if len(set(mapping.values())) != len(mapping):
        raise ValueError('Observed knob-to-burner mapping is not one-to-one')
    snapshot['knob_to_burner'] = mapping
    snapshot['burner_to_knob'] = {bid: kid for kid, bid in mapping.items()}
    snapshot['mapping_confidence'] = 'adapter_controlledObjects_unverified'
    snapshot['active_burners'] = [bid for kid, bid in mapping.items() if knobs[kid].get('isToggled', False)]
    snapshot['hazards_by_burner'] = {bid: get_nearby_hazards(snapshot, bid) for bid in burners}


def main():
    data = json.load(sys.stdin)
    if set(data) != {'action', 'observation', 'mapping_mode'}:
        raise ValueError('Only action, observation and mapping_mode are permitted')
    action, obs, mode = data['action'], data['observation'], data['mapping_mode']
    if set(action) != {'action', 'objectId', 'forceAction'} or action['action'] != 'ToggleObjectOn' or action['forceAction'] is not False:
        raise ValueError('Only an unforced ToggleObjectOn is supported')
    if set(obs) != {'objects'} or not isinstance(obs['objects'], list) or mode not in ('native', 'observed_controlled_objects'):
        raise ValueError('Invalid observation or mapping mode')
    proxy = SimpleNamespace(last_event=SimpleNamespace(metadata={'objects': copy.deepcopy(obs['objects'])}))
    snapshot = build_kitchen_snapshot(proxy)
    if mode == 'observed_controlled_objects':
        try:
            rebind(snapshot)
        except ValueError as exc:
            print(json.dumps({'status': 'MAPPING_UNAVAILABLE', 'decision': 'DEFER',
                              'mapping_mode': mode, 'reason': str(exc),
                              'physical_execution_performed': False}))
            return
    allowed, reason, details = check_toggle_scene_safety(
        {'intent': 'toggle', 'object': 'StoveKnob', 'knob_id': action['objectId'], 'knob_index': None}, snapshot)
    print(json.dumps({'status': 'COMPLETED', 'decision': 'ALLOW' if allowed else 'BLOCK',
                      'mapping_mode': mode, 'reason': reason, 'details': details,
                      'physical_execution_performed': False}, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
