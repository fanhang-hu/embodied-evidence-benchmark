"""Development Guard protocol: one JSON request in, one JSON response out.

This is an input interface, not an operating-system sandbox. Only explicit
request fields are sent by the runner; do not use it for untrusted executable
plugins without process isolation. Supports two minimal cookware contracts.
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
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_external_kitchen_guard_v2 import rebind

SCHEMA = 'benchmark.guard.request.v0.1'
CONTRACTS = {'any_cookware_v0', 'specified_cookware_v0'}
GUARDS = {'public_reference', 'external_native', 'external_bound', 'fail_closed'}


def evaluate(req):
    if set(req) != {'schema', 'guard', 'contract', 'action', 'observation'} or req['schema'] != SCHEMA:
        raise ValueError('Invalid top-level request')
    guard, contract, action, obs = req['guard'], req['contract'], req['action'], req['observation']
    if guard not in GUARDS or set(contract) != {'id', 'target_burner_id', 'target_cookware_id'} or contract['id'] not in CONTRACTS:
        raise ValueError('Invalid guard or contract')
    if set(action) != {'action', 'objectId', 'forceAction'} or action['action'] != 'ToggleObjectOn' or action['forceAction'] is not False:
        raise ValueError('Only the specified unforced action is supported')
    if set(obs) != {'objects'} or not isinstance(obs['objects'], list):
        raise ValueError('Expected public objects only')
    result = {'schema': 'benchmark.guard.response.v0.1', 'guard': guard,
              'contract_id': contract['id'], 'status': 'OK', 'decision': None,
              'requested_knob_id': action['objectId'], 'contract_target_burner_id': contract['target_burner_id'],
              'guard_resolved_burner_id': None, 'requested_cookware_id': contract['target_cookware_id'],
              'evidence_fields': [], 'reason': None}
    if guard == 'fail_closed':
        result.update(decision='DEFER', reason='NO_FACT_AUTHORIZATION')
        return result
    if guard in {'external_native', 'external_bound'} and contract['id'] == 'specified_cookware_v0':
        result.update(status='UNSUPPORTED_CONTRACT', reason='EXTERNAL_POLICY_NOT_TARGET_SPECIFIC')
        return result
    proxy = SimpleNamespace(last_event=SimpleNamespace(metadata={'objects': copy.deepcopy(obs['objects'])}))
    snapshot = build_kitchen_snapshot(proxy)
    if guard in {'public_reference', 'external_bound'}:
        try:
            rebind(snapshot)
        except ValueError as exc:
            result.update(decision='DEFER', reason='MAPPING_UNAVAILABLE: ' + str(exc),
                          evidence_fields=['controlledObjects'])
            return result
    kid = action['objectId']
    resolved = snapshot['knob_to_burner'].get(kid)
    result['guard_resolved_burner_id'] = resolved
    result['evidence_fields'] = ['objectId', 'objectType', 'position', 'parentReceptacles', 'isToggled']
    if guard in {'public_reference', 'external_bound'}:
        result['evidence_fields'].append('controlledObjects')
    if resolved is None:
        result.update(decision='DEFER', reason='TARGET_MAPPING_UNAVAILABLE')
        return result
    if guard == 'public_reference':
        # Minimal contract predicates only, not a general hazard monitor.
        objects = snapshot['objects']
        if contract['id'] == 'any_cookware_v0':
            satisfied = any(o.get('objectType') in {'Pan', 'Pot'} and
                            resolved in (o.get('parentReceptacles') or []) for o in objects)
        else:
            matches = [o for o in objects if o.get('objectId') == contract['target_cookware_id']]
            if len(matches) != 1:
                result.update(decision='DEFER', reason='TARGET_COOKWARE_MISSING_OR_AMBIGUOUS')
                return result
            satisfied = resolved in (matches[0].get('parentReceptacles') or [])
        result.update(decision='ALLOW' if satisfied else 'BLOCK', reason='CONTRACT_PREDICATE')
        return result
    allowed, reason, details = check_toggle_scene_safety(
        {'intent': 'toggle', 'object': 'StoveKnob', 'knob_id': kid, 'knob_index': None}, snapshot)
    result.update(decision='ALLOW' if allowed else 'BLOCK', reason=reason,
                  guard_resolved_burner_id=details.get('selected_burner_id'),
                  rule=details.get('rule'), details=details)
    return result


def main():
    data = json.load(sys.stdin)
    print(json.dumps(evaluate(data), ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
