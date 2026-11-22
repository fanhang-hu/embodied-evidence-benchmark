"""Offline, input-bounded adapter for the external kitchen toggle-safety component.

Input: JSON object with exactly action and observation.  No evaluator labels or
private snapshots. Output is a decision probe, not a native execution result.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'external/safe-hierarchical-embodied-ai/src'))
from ae_rl.execution.kitchen_safety import build_kitchen_snapshot, check_toggle_scene_safety


def main():
    payload = json.load(sys.stdin)
    if set(payload) != {'action', 'observation'}:
        raise ValueError('Only action and observation are permitted')
    action, observation = payload['action'], payload['observation']
    if set(action) != {'action', 'objectId', 'forceAction'} or action['action'] != 'ToggleObjectOn' or action['forceAction'] is not False:
        raise ValueError('Only an unforced, target-bound ToggleObjectOn is supported')
    if set(observation) != {'objects'} or not isinstance(observation['objects'], list):
        raise ValueError('Expected only the public objects observation')
    proxy = SimpleNamespace(last_event=SimpleNamespace(metadata={'objects': copy.deepcopy(observation['objects'])}))
    snapshot = build_kitchen_snapshot(proxy)
    allowed, reason, details = check_toggle_scene_safety(
        {'intent': 'toggle', 'object': 'StoveKnob', 'knob_id': action['objectId'], 'knob_index': None}, snapshot)
    result = dict(adapter='external_kitchen_toggle_component', native_guard_decision='ALLOW' if allowed else 'BLOCK',
                  reason=reason, details=details, action=action,
                  controller_redirect_applied=False, physical_execution_performed=False)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
