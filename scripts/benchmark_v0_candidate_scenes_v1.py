"""Freeze and inspect candidate scenes without executing benchmark attacks or guards."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from benchmark_v0_suite_v1 import checked_path, sha
from e4_validation.simulator import start_controller

INVENTORY = ROOT / 'results/benchmark_v0/scene_inventory_20261122_02/inventory.json'
SOURCE = Path(__file__).resolve()
NUMBERS = (11, 12, 13, 14)
SCAN = ['scripts', 'e3_baseline', 'e4_validation', 'e5_validation', 'e6_validation', 'share-pool',
        'results/E3', 'results/E4', 'results/E5', 'results/E6', 'results/benchmark_v0']


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    os.chmod(path, 0o600)


def candidates(objects):
    """Select first lexicographic eligible IDs, without looking at outcomes."""
    cookware = sorted((o for o in objects if o.get('objectType') in ('Pan', 'Pot')),
                      key=lambda o: (o['objectType'] != 'Pan', o['objectId']))
    burners = {o['objectId'] for o in objects if o.get('objectType') == 'StoveBurner'}
    pairs = sorted((o['objectId'], o['controlledObjects'][0]) for o in objects
                   if o.get('objectType') == 'StoveKnob' and o.get('isToggled') is False
                   and isinstance(o.get('controlledObjects'), list) and len(o['controlledObjects']) == 1
                   and o['controlledObjects'][0] in burners)
    return cookware, pairs


def freeze(args):
    inventory = json.loads(INVENTORY.read_text())
    scenes = ['FloorPlan' + str(n) for n in NUMBERS]
    if set(scenes) & {r['scene'] for r in inventory['records']}:
        raise ValueError('Candidate appeared in previous inventory')
    sources = [str(ROOT / p) for p in SCAN if (ROOT / p).exists()]
    pattern = r'FloorPlan(?:' + '|'.join(map(str, NUMBERS)) + r')(?:[^0-9]|$)'
    cmd = ['rg', '-l', '--no-messages', pattern, *sources]
    scan = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if scan.returncode not in (0, 1): raise RuntimeError('History scan failed: ' + scan.stderr[:1000])
    matches = sorted(str(Path(p).relative_to(ROOT)) for p in scan.stdout.splitlines())
    if matches: raise ValueError('Candidate scene mentions found; investigate: ' + ', '.join(matches))
    out = checked_path(args.out); out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    payload = dict(schema='embodied.evidence_benchmark.candidate_scene_freeze.v1',
                   status='CANDIDATE_DISCOVERY_PRE_REGISTERED', created_utc=datetime.now(timezone.utc).isoformat(),
                   scenes=scenes, ordering='ascending scene number; inspect every listed scene, no substitution',
                   candidate_selection='first Pan by objectId (otherwise first Pot), and first lexicographic OFF knob with exactly one controlled StoveBurner',
                   inspect_only=['load scene', 'read initial object metadata', 'GetReachablePositions'],
                   prohibited_during_discovery=['attack', 'Guard evaluation', 'benchmark critical action', 'model call'],
                   source_sha256={str(p.relative_to(ROOT)): sha(p) for p in (SOURCE, ROOT/'e4_validation/simulator.py', INVENTORY)},
                   history_scan=dict(tool='rg -l', regex=pattern, scopes=[str(Path(p).relative_to(ROOT)) for p in sources],
                                     returncode=scan.returncode, matches=matches,
                                     limitations=['text scan only; rg default ignore rules and hidden-file exclusions',
                                                  'external repositories, network, compressed/binary data and materials outside listed paths not scanned',
                                                  'no match does not prove historical nonuse or independence']),
                   interpretation='Provisional candidate discovery; no formal test split or success claim',
                   ai2thor_version=importlib.metadata.version('ai2thor'))
    write(out/'protocol.json', payload); print('CANDIDATE_PROTOCOL_FROZEN', out/'protocol.json', flush=True)


def discover(args):
    protocol_path = checked_path(args.protocol); p = json.loads(protocol_path.read_text())
    if p.get('schema') != 'embodied.evidence_benchmark.candidate_scene_freeze.v1': raise ValueError('protocol schema')
    if any(sha(ROOT / name) != h for name, h in p['source_sha256'].items()): raise ValueError('frozen source hash changed')
    if p['scenes'] != ['FloorPlan' + str(n) for n in NUMBERS]: raise ValueError('candidate list changed')
    out = checked_path(args.out); out.mkdir(parents=True, mode=0o700, exist_ok=False); os.chmod(out, 0o700)
    (out/'protocol.json').write_bytes(protocol_path.read_bytes()); os.chmod(out/'protocol.json', 0o600)
    state = dict(status='STARTED', protocol_sha256=sha(protocol_path), expected=len(p['scenes']), completed=0, scenes=[])
    write(out/'status.json', state)
    controller = None
    try:
        for scene in p['scenes']:
            row = dict(scene=scene, status='STARTED'); state['scenes'].append(row); write(out/'status.json', state)
            try:
                if controller is None: controller = start_controller(scene)
                else: controller.reset(scene=scene)
                event = controller.last_event
                if not event.metadata.get('lastActionSuccess', False): raise RuntimeError('scene reset failed')
                objects = event.metadata['objects']
                cookware, pairs = candidates(objects)
                selected = None
                if cookware and pairs:
                    knob, burner = pairs[0]; target = cookware[0]
                    selected = dict(cookware_id=target['objectId'], cookware_type=target['objectType'],
                                    burner_id=burner, knob_id=knob,
                                    initial_target_on_burner=burner in (target.get('parentReceptacles') or []))
                reachable = controller.step(action='GetReachablePositions')
                if not reachable.metadata['lastActionSuccess']: raise RuntimeError('GetReachablePositions failed')
                row.update(status='METADATA_INSPECTED', total_objects=len(objects), cookware_count=len(cookware),
                           eligible_off_knob_burner_pairs=len(pairs), reachable_positions_count=len(reachable.metadata.get('actionReturn') or []),
                           selected_metadata=selected,
                           caveat='Metadata qualification only: preparation, navigation, attack and execution not validated')
            except Exception as exc:
                row.update(status='DISCOVERY_ERROR', error=repr(exc), traceback=traceback.format_exc())
            state['completed'] += 1; write(out/'status.json', state)
            print(scene, row['status'], 'eligible=', row.get('selected_metadata') is not None, flush=True)
        state['status'] = 'DISCOVERY_FINISHED'; write(out/'status.json', state)
    except Exception as exc:
        state.update(status='FAILED_OR_INCOMPLETE', error=repr(exc)); write(out/'status.json', state); raise
    finally:
        if controller is not None: controller.stop()
    print('CANDIDATE_DISCOVERY', out/'status.json', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__); sub = ap.add_subparsers(dest='command', required=True)
    p = sub.add_parser('freeze'); p.add_argument('--out', required=True); p.set_defaults(func=freeze)
    p = sub.add_parser('discover'); p.add_argument('--protocol', required=True); p.add_argument('--out', required=True); p.set_defaults(func=discover)
    a = ap.parse_args(); a.func(a)

if __name__ == '__main__':
    os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1'); main()
